"""Opt-in corporate administrator mutations with exact group and Atlas grant boundaries."""

from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, StringConstraints
from sqlalchemy import select, update

from otm.auth.administrators import AdministratorChange, AdministratorFailure, AdministratorView
from otm.auth.corporate_enrollment import (
    CorporateLookup,
    DomainPerson,
    Enrollment,
    EnrollmentReview,
    EnrollmentTarget,
    NewAccountName,
    federated_user_request,
    membership_request,
    prepare_enrollment,
    read_domain_person,
    verify_domain_person,
)
from otm.auth.service import AdminPrincipal
from otm.operations.contracts import canonical_hash
from otm.storage.administrators import SqlAdministratorStore, administrator_record
from otm.storage.security_events import corporate_grant_event
from otm.storage.tables import administrator


# Return verified display details and a fingerprint bound to the reviewed identity and grant.
class AdministratorPreview(EnrollmentReview):
    confirmation: str


# Bind confirmation to the original lookup and accept names only for new accounts.
class ConfirmAdministrator(CorporateLookup):
    confirmation: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    name: NewAccountName | None = Field(default=None, repr=False)


# Distinguish a committed Atlas revoke from a failed external cleanup.
class CorporateRemoval(AdministratorChange):
    group_cleanup: Literal["complete", "pending"]


# Let qualified providers identify create conflicts without returning private diagnostics.
class FederatedCreateConflict(RuntimeError):
    pass


# Scope interactive mutation orchestration to one environment and one explicitly qualified adapter.
class CorporateAdministrators:
    # Require exact OCI readback. The adapter must settle ambiguous writes before allowing an
    # opposite mutation, since a PostgreSQL lock cannot fence an outstanding OCI request.
    # Provider operations held under the recovery-row lock must have a strict total deadline.
    # An optional creator must deduplicate each retry key and fence unresolved creates for the
    # same domain and identity across sessions, including after a lost response or restart.
    def __init__(
        self,
        store: SqlAdministratorStore,
        target: EnrollmentTarget,
        domain_lookup: Callable,
        membership: Callable,
        create: Callable | None = None,
    ):
        if target.issuer == store.local_issuer or target.issuer not in store.trusted_issuers:
            raise ValueError("UNTRUSTED_CORPORATE_ADMINISTRATOR_TARGET")
        self.store, self.target = store, target
        self.domain_lookup = domain_lookup
        self.membership, self.create = membership, create

    # Never run identity or group operations from a different Atlas workspace.
    def _scope(self, principal: AdminPrincipal):
        if (
            not isinstance(principal, AdminPrincipal)
            or principal.session.workspace_id != self.target.workspace
        ):
            raise AdministratorFailure(403, "ADMINISTRATOR_REQUIRED")

    # Resolve provider facts independently from the Atlas database and organization feed.
    def _resolve(self, lookup: CorporateLookup):
        try:
            return prepare_enrollment(lookup, self.target, self.domain_lookup)
        except ValueError:
            raise AdministratorFailure(422, "CORPORATE_IDENTITY_UNVERIFIED") from None

    # Load only the grant for the exact corporate subject in this installation.
    def _subject(self, connection, guid):
        row = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == self.target.workspace,
                    administrator.c.issuer == self.target.issuer,
                    administrator.c.subject == guid,
                )
            )
            .mappings()
            .one_or_none()
        )
        return administrator_record(row) if row is not None else None

    # Bind confirmation to the validated identity, actor session, and existing grant revision.
    def _confirmation(self, connection, enrollment: Enrollment, principal: AdminPrincipal):
        if enrollment.account is None and self.create is None:
            raise AdministratorFailure(422, "CORPORATE_IDENTITY_UNVERIFIED")
        existing = (
            self._subject(connection, enrollment.account.guid) if enrollment.account else None
        )
        if existing and existing.status == "active":
            raise AdministratorFailure(409, "ADMINISTRATOR_ALREADY_ACTIVE")
        confirmation = canonical_hash(
            {
                "binding": enrollment.binding(),
                "session": str(principal.session.id),
                "grant_revision": str(existing.authorization_revision) if existing else None,
            }
        )
        return existing, confirmation

    # Review performs only qualified reads and never changes OCI or Atlas state.
    def preview(self, principal: AdminPrincipal, lookup: CorporateLookup):
        self._scope(principal)
        with self.store.engine.connect() as connection:
            self.store.current_actor(connection, principal)
        enrollment = self._resolve(lookup)
        with self.store.engine.connect() as connection:
            self.store.current_actor(connection, principal)
            _, confirmation = self._confirmation(connection, enrollment, principal)
        return AdministratorPreview(**enrollment.review().model_dump(), confirmation=confirmation)

    # Require the OCI GUID and exact federated login to match independent readback.
    def _provision(self, enrollment: Enrollment, name: NewAccountName) -> DomainPerson:
        payload = federated_user_request(enrollment, name)
        retry_key = canonical_hash(
            {
                "domain": self.target.domain,
                "user": payload,
            }
        )
        receipt = None
        try:
            receipt = DomainPerson.model_validate(self.create(payload, retry_key))
            verify_domain_person(self.target, enrollment.email, receipt)
            if not receipt.federated:
                raise ValueError("FEDERATED_CREATE_REQUIRED")
        except (TimeoutError, FederatedCreateConflict):
            # Read back once. The adapter owns reconciliation if a later request retries.
            pass
        except ValueError:
            raise AdministratorFailure(422, "CORPORATE_IDENTITY_UNVERIFIED") from None
        try:
            account = read_domain_person(self.target, enrollment.email, self.domain_lookup)
        except ValueError:
            raise AdministratorFailure(422, "CORPORATE_IDENTITY_UNVERIFIED") from None
        if account is None or (receipt is not None and receipt.guid != account.guid):
            raise AdministratorFailure(503, "ADMINISTRATOR_SERVICE_UNAVAILABLE")
        if not account.federated:
            raise AdministratorFailure(422, "CORPORATE_IDENTITY_UNVERIFIED")
        return account

    # Keep the group update ahead of local access and hold the same lock used by revoke and retry.
    def confirm(self, principal: AdminPrincipal, command: ConfirmAdministrator):
        self._scope(principal)
        with self.store.engine.begin() as connection:
            self.store.lock_administration(connection, self.target.workspace)
            self.store.current_actor(connection, principal)
            enrollment = self._resolve(command)
            existing, confirmation = self._confirmation(connection, enrollment, principal)
            if confirmation != command.confirmation:
                raise AdministratorFailure(409, "ADMINISTRATOR_CONFIRMATION_CHANGED")
            account = enrollment.account
            if account is None:
                if command.name is None:
                    raise AdministratorFailure(400, "INVALID_ADMINISTRATOR_COMMAND")
                self.store.current_actor(connection, principal)
                account = self._provision(enrollment, command.name)
                if self._subject(connection, account.guid) is not None:
                    raise AdministratorFailure(409, "ADMINISTRATOR_CONFIRMATION_CHANGED")
            elif command.name is not None:
                raise AdministratorFailure(400, "INVALID_ADMINISTRATOR_COMMAND")
            self.store.current_actor(connection, principal)
            if (
                self.membership(
                    *membership_request(self.target, account.guid, add=True),
                    authorize=lambda: self.store.current_actor(connection, principal),
                )
                is not True
            ):
                raise AdministratorFailure(503, "ADMINISTRATOR_SERVICE_UNAVAILABLE")
            at = self.store.current_actor(connection, principal)
            identifier, revision = (existing.id if existing else uuid4()), uuid4()
            values = dict(
                status="active",
                authorization_revision=revision,
                updated_at=at,
                revoked_at=None,
                display_name=account.display_name or enrollment.email,
                email=enrollment.email,
            )
            if existing:
                connection.execute(
                    update(administrator)
                    .where(administrator.c.id == identifier)
                    .values(**values, group_cleanup_complete=False)
                )
            else:
                connection.execute(
                    administrator.insert().values(
                        id=identifier,
                        workspace_id=self.target.workspace,
                        identity_kind="corporate_sso",
                        issuer=self.target.issuer,
                        subject=account.guid,
                        created_at=at,
                        **values,
                    )
                )
            corporate_grant_event(
                connection,
                workspace=self.target.workspace,
                grant_id=identifier,
                actor=principal.actor,
                at=at,
                revision=revision,
                previous_revision=existing.authorization_revision if existing else None,
            )
            return AdministratorView(
                id=identifier,
                display_name=values["display_name"],
                email=values["email"],
                identity_kind="corporate_sso",
                status="active",
                authorization_revision=revision,
            )

    # Keep the established local transaction authoritative even when OCI is unavailable.
    def remove(self, principal: AdminPrincipal, identifier: UUID, revision: UUID):
        self._scope(principal)
        self._target(identifier)
        change = self.store.revoke(principal, identifier, revision)
        try:
            return self.cleanup(principal, identifier, change.authorization_revision)
        except Exception:
            return CorporateRemoval(**change.model_dump(), group_cleanup="pending")

    # Resolve the exact environment's corporate grant or refuse any external operation.
    def _target(self, identifier: UUID, connection=None):
        if connection is None:
            with self.store.engine.connect() as live:
                return self._target(identifier, live)
        row = (
            connection.execute(
                select(administrator).where(
                    administrator.c.id == identifier,
                    administrator.c.workspace_id == self.target.workspace,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise AdministratorFailure(404, "ADMINISTRATOR_NOT_FOUND")
        if row["identity_kind"] == "local_recovery":
            raise AdministratorFailure(403, "RECOVERY_ADMINISTRATOR_PROTECTED")
        if row["identity_kind"] != "corporate_sso" or row["issuer"] != self.target.issuer:
            raise AdministratorFailure(404, "ADMINISTRATOR_NOT_FOUND")
        return administrator_record(row)

    # Hold the lock until OCI readback so an old retry cannot remove a later regrant.
    def cleanup(self, principal: AdminPrincipal, identifier: UUID, revision: UUID):
        self._scope(principal)
        with self.store.engine.begin() as connection:
            self.store.lock_administration(connection, self.target.workspace)
            self.store.current_actor(connection, principal)
            grant = self._target(identifier, connection)
            if grant.status != "revoked" or grant.authorization_revision != revision:
                raise AdministratorFailure(409, "ADMINISTRATOR_REVISION_CHANGED")
            complete = connection.scalar(
                select(administrator.c.group_cleanup_complete).where(
                    administrator.c.id == grant.id,
                    administrator.c.workspace_id == self.target.workspace,
                )
            )
            done = (
                complete is True
                or self.membership(
                    *membership_request(self.target, grant.subject, add=False),
                    authorize=lambda: self.store.current_actor(connection, principal),
                )
                is True
            )
            if done and complete is not True:
                connection.execute(
                    update(administrator)
                    .where(
                        administrator.c.id == grant.id,
                        administrator.c.workspace_id == self.target.workspace,
                        administrator.c.status == "revoked",
                        administrator.c.authorization_revision == revision,
                    )
                    .values(group_cleanup_complete=True)
                )
            return CorporateRemoval(
                administrator_id=grant.id,
                status="revoked",
                authorization_revision=revision,
                at=grant.revoked_at,
                group_cleanup="complete" if done is True else "pending",
            )
