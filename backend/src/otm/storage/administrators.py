"""Current OTM grants and atomic revocation; no bootstrap, account creation or IdP lookup."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.engine import Connection, Engine

from otm.auth.administrators import (
    Administrator,
    AdministratorChange,
    AdministratorDirectory,
    AdministratorFailure,
    AdministratorQuery,
    AdministratorRevoked,
    AdministratorStatistics,
    AdministratorView,
)
from otm.auth.contracts import AdminEntitlement
from otm.auth.service import AdminPrincipal
from otm.contracts import Text, UtcInstant
from otm.operations.contracts import canonical_hash
from otm.storage.sessions import invalid_session, session_record
from otm.storage.tables import admin_session, administrator, audit_event
from otm.storage.transaction import require_transaction


# Normalize aware database instants without relabeling naive or otherwise malformed timestamps.
def administrator_record(row) -> Administrator:
    values = dict(row)
    for name in ("created_at", "updated_at", "revoked_at"):
        value = values[name]
        if value is not None:
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError("INVALID_ADMINISTRATOR_TIMESTAMP")
            values[name] = value.astimezone(UTC)
    return Administrator.model_validate(values)


# Share exact issuer registration and current grant reads with internal management transactions.
class SqlAdministratorStore:
    # Require explicit issuer policy and server clock; constructing the store grants no account.
    def __init__(
        self,
        engine: Engine,
        clock: Callable[[], datetime],
        *,
        local_issuer: str,
        trusted_issuers: frozenset[str],
    ):
        self.local_issuer = TypeAdapter(Text).validate_python(local_issuer)
        if (
            not isinstance(trusted_issuers, frozenset)
            or local_issuer not in trusted_issuers
            or any(not TypeAdapter(Text).validate_python(value) for value in trusted_issuers)
        ):
            raise ValueError("EXPLICIT_ADMINISTRATOR_ISSUERS_REQUIRED")
        self.engine, self.clock, self.trusted_issuers = engine, clock, trusted_issuers

    # Validate row invariants and namespace instead of treating presence as authorization.
    def _grant(self, connection: Connection, workspace: str, issuer: str, subject: str):
        if issuer not in self.trusted_issuers:
            raise PermissionError("ADMINISTRATOR_REQUIRED")
        row = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == workspace,
                    administrator.c.issuer == issuer,
                    administrator.c.subject == subject,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PermissionError("ADMINISTRATOR_REQUIRED")
        grant = administrator_record(row)
        if grant.status != "active" or (
            (grant.identity_kind == "local_recovery") != (issuer == self.local_issuer)
        ):
            raise PermissionError("ADMINISTRATOR_REQUIRED")
        return grant

    # Resolve fresh local grants; corporate provider status still needs its qualified composition.
    def require_admin(self, issuer: str, subject: str, workspace_id: str) -> AdminEntitlement:
        with self.engine.connect() as connection:
            grant = self._grant(connection, workspace_id, issuer, subject)
        at = TypeAdapter(UtcInstant).validate_python(self.clock())
        return AdminEntitlement(
            workspace_id=grant.workspace_id,
            issuer=grant.issuer,
            subject=grant.subject,
            reference=str(grant.id),
            revision=grant.authorization_revision,
            checked_at=at,
            valid_until=at + timedelta(seconds=5),
        )

    # Sanitize the whole mutation boundary, including failed COMMIT and malformed trusted output.
    def revoke(self, principal: object, target_id: UUID, expected_revision: UUID):
        if not isinstance(principal, AdminPrincipal):
            raise AdministratorFailure(403, "ADMINISTRATOR_REQUIRED")
        if not isinstance(target_id, UUID) or not isinstance(expected_revision, UUID):
            raise AdministratorFailure(400, "INVALID_ADMINISTRATOR_COMMAND")
        try:
            return self._revoke(principal, target_id, expected_revision)
        except AdministratorFailure:
            raise
        except PermissionError:
            raise AdministratorFailure(403, "ADMINISTRATOR_REQUIRED") from None
        except Exception:
            raise AdministratorFailure(503, "ADMINISTRATOR_SERVICE_UNAVAILABLE") from None

    # Serialize scope changes on the protected row, then recheck live actor/session under that lock.
    def _revoke(self, principal: AdminPrincipal, target_id: UUID, expected_revision: UUID):
        presented = principal.session
        workspace = presented.workspace_id
        with self.engine.begin() as connection:
            require_transaction(connection)
            anchor = connection.execute(
                select(administrator.c.id)
                .where(
                    administrator.c.workspace_id == workspace,
                    administrator.c.identity_kind == "local_recovery",
                    administrator.c.status == "active",
                )
                .with_for_update()
            ).scalar_one_or_none()
            if anchor is None:
                raise AdministratorFailure(503, "ADMINISTRATOR_SERVICE_UNAVAILABLE")
            at = TypeAdapter(UtcInstant).validate_python(self.clock())
            stored = session_record(
                connection.execute(
                    select(admin_session).where(
                        admin_session.c.id == presented.id,
                        admin_session.c.workspace_id == workspace,
                        admin_session.c.session_token_hash == presented.session_token_hash,
                        ~invalid_session(at),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                stored is None
                or not stored.auth_time <= stored.created_at <= at
                or (stored.issuer, stored.subject)
                != (
                    presented.issuer,
                    presented.subject,
                )
            ):
                raise PermissionError("ADMINISTRATOR_REQUIRED")
            actor = self._grant(connection, workspace, stored.issuer, stored.subject)
            if (
                stored.entitlement_reference != str(actor.id)
                or stored.entitlement_revision != actor.authorization_revision
            ):
                raise PermissionError("ADMINISTRATOR_REQUIRED")
            row = (
                connection.execute(
                    select(administrator)
                    .where(
                        administrator.c.workspace_id == workspace,
                        administrator.c.id == target_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise AdministratorFailure(404, "ADMINISTRATOR_NOT_FOUND")
            target = administrator_record(row)
            if target.identity_kind == "local_recovery":
                raise AdministratorFailure(403, "RECOVERY_ADMINISTRATOR_PROTECTED")
            if target.authorization_revision != expected_revision:
                raise AdministratorFailure(409, "ADMINISTRATOR_REVISION_CHANGED")
            if target.status == "revoked":
                return AdministratorChange(
                    administrator_id=target.id,
                    status="revoked",
                    authorization_revision=target.authorization_revision,
                    at=target.revoked_at,
                )
            revision = uuid4()
            connection.execute(
                update(administrator)
                .where(administrator.c.id == target.id)
                .values(
                    status="revoked",
                    authorization_revision=revision,
                    updated_at=at,
                    revoked_at=at,
                )
            )
            connection.execute(
                update(admin_session)
                .where(
                    admin_session.c.workspace_id == workspace,
                    admin_session.c.issuer == target.issuer,
                    admin_session.c.subject == target.subject,
                    admin_session.c.revoked_at.is_(None),
                )
                .values(revoked_at=at)
            )
            actor_snapshot = principal.actor
            evidence = AdministratorRevoked(
                contract_version="administrator-revocation-1",
                administrator_id=target.id,
                prior_revision=target.authorization_revision,
                authorization_revision=revision,
                actor=actor_snapshot,
            )
            data = evidence.model_dump(mode="json")
            connection.execute(
                audit_event.insert().values(
                    id=uuid4(),
                    workspace_id=workspace,
                    operation_id=None,
                    administrator_id=target.id,
                    intent_revision=None,
                    actor=actor_snapshot.key,
                    actor_subject=actor_snapshot.key,
                    actor_snapshot=actor_snapshot.model_dump(mode="json"),
                    kind="administrator_revoked",
                    at=at,
                    contract_version=evidence.contract_version,
                    data=data,
                    data_hash=canonical_hash(data),
                )
            )
            result = AdministratorChange(
                administrator_id=target.id,
                status="revoked",
                authorization_revision=revision,
                at=at,
            )
        return result

    # Page only the server-authorized workspace, with allowlisted sorting and escaped search values.
    def directory(self, workspace: str, query: AdministratorQuery) -> AdministratorDirectory:
        query = AdministratorQuery.model_validate(query)
        where = [administrator.c.workspace_id == workspace]
        if query.query:
            where.append(
                or_(
                    administrator.c.display_name.icontains(query.query, autoescape=True),
                    administrator.c.email.icontains(query.query, autoescape=True),
                )
            )
        column = {
            "display_name": administrator.c.display_name,
            "email": administrator.c.email,
            "identity_kind": administrator.c.identity_kind,
            "status": administrator.c.status,
        }[query.sort]
        order = (column.asc() if query.direction == "asc" else column.desc()).nulls_last()
        with self.engine.connect() as connection:
            counts = connection.execute(
                select(
                    func.count(),
                    func.coalesce(
                        func.sum(case((administrator.c.status == "active", 1), else_=0)), 0
                    ),
                    func.coalesce(
                        func.sum(
                            case((administrator.c.identity_kind == "local_recovery", 1), else_=0)
                        ),
                        0,
                    ),
                ).where(administrator.c.workspace_id == workspace)
            ).one()
            total = connection.scalar(select(func.count()).select_from(administrator).where(*where))
            pages = max(1, (total + query.page_size - 1) // query.page_size)
            page = min(query.page, pages)
            rows = (
                connection.execute(
                    select(*[administrator.c[key] for key in AdministratorView.model_fields])
                    .where(*where)
                    .order_by(order, administrator.c.id)
                    .offset((page - 1) * query.page_size)
                    .limit(query.page_size)
                )
                .mappings()
                .all()
            )
        return AdministratorDirectory(
            items=[AdministratorView(**row) for row in rows],
            total=total,
            page=page,
            page_size=query.page_size,
            pages=pages,
            statistics=AdministratorStatistics(
                total=counts[0], active=counts[1], protected_recovery=counts[2]
            ),
        )
