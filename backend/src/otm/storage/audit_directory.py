"""Workspace-scoped immutable history projections with no raw audit payload serialization."""

import json
from datetime import UTC

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.engine import Engine

from otm.audit.contracts import (
    AuditDirectory,
    AuditEntry,
    AuditExportEvidence,
    AuditExportQuery,
    AuditQuery,
    AuditResource,
)
from otm.audit.descriptions import describe_organization
from otm.configuration.contracts import (
    BaselineDraftEvidence,
    BaselinePublicationEvidence,
    BaselineSelectionEvidence,
    describe_draft,
)
from otm.configuration.drift_contracts import ConfigurationCheckEvidence
from otm.configuration.override_contracts import ConfigurationReviewEvidence
from otm.configuration.rollout_contracts import ConfigurationOutcome, ConfigurationRetryEvidence
from otm.financial.contracts import CostEvidence, CostRefreshReceipt
from otm.notifications.contracts import NotificationEvidence
from otm.operations.contracts import ActorIdentity, IntentEventData, canonical_hash
from otm.operations.execution_contracts import InspectionOutcome
from otm.operations.responsibility import decode_evidence
from otm.organization.persistence_contracts import ORGANIZATION_SERVICE_ACTOR, OrganizationEvidence
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import administrator, audit_event, tenancy
from otm.tenancies.contracts import OrganizationActionOutcome
from otm.tenancies.onboarding_contracts import OnboardingEvidence
from otm.tenancies.presence_contracts import PresenceCheckEvidence
from otm.tenancies.recovery_network_contracts import RecoveryNetworkEvidence
from otm.tenancies.recovery_password_contracts import (
    RecoveryDisclosureEvidence,
    RecoveryPasswordEvidence,
)
from otm.tenancies.signing_key_contracts import SigningKeyEvidence, SigningKeyRequestEvidence

AUTHENTICATION = ("local_sign_in_succeeded", "local_sign_in_failed", "session_logged_out")
ADMINISTRATION = (
    "configuration_review_staged",
    "baseline_draft_saved",
    "baseline_published",
    "baseline_default_changed",
    "administrator_revoked",
    "administrator_bootstrapped",
    "local_credentials_reset",
    "audit_export",
)
EMAIL_DELIVERY = ("email_delivery",)
OPERATIONS = (
    "signing_key_outcome",
    "signing_key_requested",
    "operation_responsibility_changed",
    "configuration_check_outcome",
    "cost_collection_outcome",
    "required_user_check_outcome",
    "recovery_network_outcome",
    "recovery_password_outcome",
    "recovery_password_disclosed",
    "cost_refresh_requested",
    "operation_intent",
    "inspection_dispatch",
    "inspection_outcome",
    "organization_action_outcome",
    "onboarding_action",
    "onboarding_outcome",
    "configuration_outcome",
    "configuration_retry",
)
ORGANIZATION = (
    "organization_configured",
    "organization_feed_received",
    "organization_feed_rejected",
    "organization_published",
    "organization_review_decided",
)


# Failed proofs expose no verified actor or attempted username; operator labels stay generic.
def actor_expression():
    return case(
        (audit_event.c.kind == "required_user_check_outcome", "User presence worker"),
        (audit_event.c.kind == "recovery_network_outcome", "Recovery network worker"),
        (audit_event.c.kind == "recovery_password_outcome", "Recovery password worker"),
        (audit_event.c.kind == "signing_key_outcome", "Signing-key worker"),
        (audit_event.c.kind == "cost_collection_outcome", "Cost collection worker"),
        (audit_event.c.kind == "local_sign_in_failed", None),
        (
            audit_event.c.kind.in_(("inspection_dispatch", "inspection_outcome")),
            "Inspection worker",
        ),
        (
            audit_event.c.actor_snapshot["issuer"].astext == "urn:otm:database-operator",
            "Database operator",
        ),
        (
            audit_event.c.kind.in_(("organization_action_outcome", "onboarding_outcome")),
            "Organization worker",
        ),
        else_=audit_event.c.actor_snapshot["display_name"].astext,
    )


# Return only public context while retaining the full immutable authoritative row in PostgreSQL.
def entry(row):
    if canonical_hash(row["data"]) != row["data_hash"]:
        raise ValueError("INVALID_AUDIT_EVIDENCE")
    kind = row["kind"]
    summary, changes = None, ()
    baseline_id = None
    if kind == "baseline_draft_saved":
        evidence = BaselineDraftEvidence.model_validate_json(json.dumps(row["data"]))
        baseline_id = evidence.baseline_id
        summary = (
            f"Saved baseline draft v{evidence.version_number}, revision {evidence.edit_revision}"
        )
        changes = describe_draft(evidence)
    if kind == "baseline_published":
        published = BaselinePublicationEvidence.model_validate_json(json.dumps(row["data"]))
        if (
            published.baseline.published_by != row["actor_subject"]
            or published.baseline.published_at != row["at"]
            or published.baseline.published_by_name
            != (row["actor_snapshot"].get("display_name") or "Administrator")
        ):
            raise ValueError("INVALID_PUBLICATION_ACTOR")
        baseline_id = published.baseline.id
        summary = f"Published baseline v{published.baseline.version_number} (simulated validation)"
        changes = (
            ("Default for new simulated create/import operations.",)
            if published.default_for_new
            else ()
        ) + (
            "Local structure and USD profile checked; "
            "OCI validation and application remain pending.",
        )
    if kind == "baseline_default_changed":
        selection = BaselineSelectionEvidence.model_validate_json(json.dumps(row["data"]))
        baseline_id = selection.baseline.id
        summary = f"Selected baseline v{selection.baseline.version_number} for new tenancies"
        changes = ("Existing tenancies and already-started operations are unchanged.",)
    if kind in {"configuration_outcome", "configuration_retry"}:
        config_evidence = (
            ConfigurationOutcome if kind == "configuration_outcome" else ConfigurationRetryEvidence
        ).model_validate_json(json.dumps(row["data"]))
        baseline_id = config_evidence.baseline_id
        summary = (
            "Configuration update verified locally"
            if config_evidence.safe_code == "CONFIGURATION_VERIFIED"
            else "Configuration retry accepted"
            if kind == "configuration_retry"
            else "Configuration update needs attention"
        )
    if kind == "email_delivery":
        mail = NotificationEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Email delivery: " + mail.state
    if kind == "operation_responsibility_changed":
        proof = decode_evidence(row)
        summary = "Administrator responsibility changed"
        changes = (
            f"{proof.before_name or 'Previous administrator'} → "
            f"{proof.after_actor.display_name or 'Administrator'}",
        )
    if kind == "cost_collection_outcome":
        cost = CostEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Cost collection: " + cost.state
    if kind == "cost_refresh_requested":
        receipt = CostRefreshReceipt.model_validate_json(json.dumps(row["data"]["receipt"]))
        summary = f"Cost refresh: {receipt.accepted_count} queued, {receipt.joined_count} joined"
    if kind == "recovery_password_disclosed":
        proof = RecoveryDisclosureEvidence.model_validate_json(json.dumps(row["data"]))
        summary = (
            "Authorized recovery-password disclosure attempt; original rotation due "
            + proof.rotation_due_at.isoformat()
        )
    if kind == "recovery_password_outcome":
        proof = RecoveryPasswordEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Recovery password " + proof.phase + ": " + proof.state
    if kind == "recovery_network_outcome":
        proof = RecoveryNetworkEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Recovery network repair: " + proof.state
    if kind == "signing_key_outcome":
        proof = SigningKeyEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Automation signing-key " + proof.phase + ": " + proof.state
    if kind == "signing_key_requested":
        proof = SigningKeyRequestEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Requested original signing-key operation: " + proof.action
    if kind == "required_user_check_outcome":
        proof = PresenceCheckEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Read-only user presence check: " + proof.state
    if kind == "configuration_check_outcome":
        check = ConfigurationCheckEvidence.model_validate_json(json.dumps(row["data"]))
        summary = "Read-only configuration check: " + check.state
    if kind in ORGANIZATION:
        evidence = OrganizationEvidence.model_validate_json(json.dumps(row["data"]))
        summary, changes = describe_organization(kind, evidence)
    if kind == "configuration_review_staged":
        review = ConfigurationReviewEvidence.model_validate_json(json.dumps(row["data"]))
        baseline_id = review.baseline_id
        summary = "Staged override conflict review; no tenancy changed"
        changes = tuple(
            f"{category}: "
            f"{'Use new baseline' if choice == 'use_new_baseline' else 'Keep complete override'}"
            for category, choice in (
                ("Policy", review.policy_choice),
                ("Quota", review.quota_choice),
            )
            if choice
        )
    if kind == "audit_export":
        AuditExportEvidence.model_validate_json(json.dumps(row["data"]))
    if kind == "email_delivery":
        if row["actor_subject"] != "otm-worker:email" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "email",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Email delivery worker"
    elif kind == "signing_key_outcome":
        if row["actor_subject"] != "otm-worker:signing-key" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "signing-key",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Signing-key worker"
    elif kind == "recovery_password_outcome":
        if row["actor_subject"] != "otm-worker:recovery-password" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "recovery-password",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Recovery password worker"
    elif kind == "recovery_network_outcome":
        if row["actor_subject"] != "otm-worker:recovery-network" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "recovery-network",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Recovery network worker"
    elif kind == "required_user_check_outcome":
        if row["actor_subject"] != "otm-worker:user-presence" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "user-presence",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "User presence worker"
    elif kind == "cost_collection_outcome":
        if row["actor_subject"] != "otm-worker:costs" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "costs",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Cost collection worker"
    elif kind == "configuration_check_outcome":
        if row["actor_subject"] != "otm-worker:configuration-check" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "configuration-check",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Configuration check worker"
    elif kind == "configuration_outcome":
        if row["actor_subject"] != "otm-worker:configuration" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "configuration",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Configuration worker"
    elif kind in {"organization_action_outcome", "onboarding_outcome"}:
        if row["actor_subject"] != "otm-worker:organization" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "organization",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Organization worker"
    elif kind in {"inspection_dispatch", "inspection_outcome"}:
        if row["actor_subject"] != "otm-worker:inspection" or row["actor_snapshot"] != {
            "kind": "worker",
            "subject": "inspection",
        }:
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = "Inspection worker"
    else:
        actor = ActorIdentity.model_validate_json(json.dumps(row["actor_snapshot"]))
        if actor.key != row["actor_subject"]:
            raise ValueError("INVALID_AUDIT_ACTOR")
        if (
            kind in {"organization_published", "organization_feed_rejected"}
            and actor != ORGANIZATION_SERVICE_ACTOR
        ):
            raise ValueError("INVALID_AUDIT_ACTOR")
        actor_name = (
            None
            if kind == "local_sign_in_failed"
            else "Database operator"
            if actor.issuer == "urn:otm:database-operator"
            else actor.display_name
        )
    category = (
        "email_delivery"
        if kind in EMAIL_DELIVERY
        else "organization"
        if kind in ORGANIZATION
        else "authentication"
        if kind in AUTHENTICATION
        else "administration"
        if kind in ADMINISTRATION
        else "operations"
    )
    outcome = (
        (
            SigningKeyEvidence
            if kind == "signing_key_outcome"
            else SigningKeyRequestEvidence
            if kind == "signing_key_requested"
            else RecoveryPasswordEvidence
            if kind == "recovery_password_outcome"
            else RecoveryNetworkEvidence
            if kind == "recovery_network_outcome"
            else PresenceCheckEvidence
            if kind == "required_user_check_outcome"
            else ConfigurationOutcome
            if kind == "configuration_outcome"
            else ConfigurationRetryEvidence
            if kind == "configuration_retry"
            else OnboardingEvidence
            if kind in {"onboarding_action", "onboarding_outcome"}
            else OrganizationActionOutcome
            if kind == "organization_action_outcome"
            else InspectionOutcome
        ).model_validate_json(json.dumps(row["data"]))
        if kind
        in {
            "inspection_outcome",
            "required_user_check_outcome",
            "recovery_network_outcome",
            "recovery_password_outcome",
            "signing_key_outcome",
            "signing_key_requested",
            "configuration_outcome",
            "configuration_retry",
            "organization_action_outcome",
            "onboarding_action",
            "onboarding_outcome",
        }
        else None
    )
    return AuditEntry(
        baseline_id=baseline_id,
        summary=summary,
        changes=changes,
        id=row["id"],
        at=row["at"].astimezone(UTC),
        kind=kind,
        category=category,
        actor_name=actor_name,
        operation_id=row["operation_id"],
        administrator_id=row["administrator_id"],
        administrator_name=row["administrator_name"],
        safe_code=cost.safe_code
        if kind == "cost_collection_outcome"
        else outcome.safe_code
        if outcome
        else None,
        organization_subject_name=row["data"].get("subject_name")
        if kind == "organization_review_decided"
        else None,
    )


# Resolve scoped operation targets in batches, checking immutable intent hashes.
def resource_context(connection, workspace, rows):
    identifiers = {row["operation_id"] for row in rows if row["operation_id"]}
    if not identifiers and not any(
        row.get("kind") == "configuration_review_staged" for row in rows
    ):
        return {}
    intents = {}
    for row in connection.execute(
        select(audit_event.c.operation_id, audit_event.c.data, audit_event.c.data_hash).where(
            audit_event.c.workspace_id == workspace,
            audit_event.c.operation_id.in_(identifiers),
            audit_event.c.kind == "operation_intent",
            audit_event.c.intent_revision == 1,
        )
    ).mappings():
        if canonical_hash(row["data"]) != row["data_hash"]:
            raise ValueError("INVALID_AUDIT_EVIDENCE")
        frozen = IntentEventData.model_validate_json(json.dumps(row["data"]))
        if frozen.intent.workspace_id != workspace:
            raise ValueError("INVALID_AUDIT_SCOPE")
        intents[row["operation_id"]] = frozen.intent
    registered = {
        row["id"]: row
        for row in connection.execute(
            select(tenancy.c.id, tenancy.c.name, tenancy.c.tenancy_ocid).where(
                tenancy.c.workspace_id == workspace
            )
        ).mappings()
    }
    results = {}
    for row in rows:
        if row["kind"] == "configuration_review_staged":
            proof = ConfigurationReviewEvidence.model_validate_json(json.dumps(row["data"]))
            resource = registered.get(proof.tenancy_id)
            results[row["id"]] = (
                (AuditResource(kind="tenancy", id=proof.tenancy_id, name=resource["name"]),)
                if resource
                else ()
            )
            continue
        intent = intents.get(row["operation_id"])
        if intent is None:
            continue
        resources = []
        wanted = set()
        if intent.kind in {"required_user_check", "recovery_network_repair"}:
            wanted = {intent.snapshot.tenancy_id}
        elif intent.kind == "signing_key":
            wanted = {intent.subject.tenancy_id}
        elif intent.kind == "recovery_password":
            wanted = {intent.location.target.tenancy_id}
        elif intent.kind in {"configuration_update", "configuration_check", "cost_collection"}:
            wanted = {
                target.configuration.tenancy_id
                if intent.kind == "cost_collection"
                else target.tenancy_id
                for target in intent.targets
            }
            if row["kind"] == "cost_collection_outcome":
                wanted &= {CostEvidence.model_validate_json(json.dumps(row["data"])).tenancy_id}
            if row["kind"] == "configuration_check_outcome":
                wanted &= {
                    ConfigurationCheckEvidence.model_validate_json(
                        json.dumps(row["data"])
                    ).tenancy_id
                }
            if row["kind"] == "configuration_outcome":
                wanted &= {
                    ConfigurationOutcome.model_validate_json(json.dumps(row["data"])).tenancy_id
                }
        elif intent.kind == "organization_action":
            wanted = {a.tenancy_id for a in intent.associations}
            if intent.pending_tenancy_id:
                wanted.add(intent.pending_tenancy_id)
            if not intent.whole_tenancy_deletion:
                resources.append(
                    AuditResource(
                        kind="person", id=intent.target.person_id, name=intent.target.display_name
                    )
                )
        wanted |= {
            key
            for key, value in registered.items()
            if value["tenancy_ocid"] == intent.target.tenancy_ocid
        }
        resources.extend(
            AuditResource(kind="tenancy", id=key, name=registered[key]["name"])
            for key in sorted(wanted, key=str)
            if key in registered
        )
        results[row["id"]] = tuple(resources)
    return results


# One allowlisted query shape keeps directory and export filtering/order semantics identical.
def selection(workspace: str, query: AuditExportQuery):
    # Target names are current directory labels, not edits to the immutable event snapshot.
    # Both join keys are required: an unrelated workspace must never supply a target label.
    source = audit_event.outerjoin(
        administrator,
        and_(
            administrator.c.workspace_id == audit_event.c.workspace_id,
            administrator.c.id == audit_event.c.administrator_id,
        ),
    )
    where = [audit_event.c.workspace_id == workspace]
    if query.category:
        where.append(
            audit_event.c.kind.in_(
                {
                    "authentication": AUTHENTICATION,
                    "administration": ADMINISTRATION,
                    "operations": OPERATIONS,
                    "organization": ORGANIZATION,
                    "email_delivery": EMAIL_DELIVERY,
                }[query.category]
            )
        )
    actor = actor_expression()
    if query.query:
        where.append(
            or_(
                actor.icontains(query.query, autoescape=True),
                administrator.c.display_name.icontains(query.query, autoescape=True),
                *[
                    cast(column, String).icontains(query.query, autoescape=True)
                    for column in (
                        audit_event.c.id,
                        audit_event.c.operation_id,
                        audit_event.c.administrator_id,
                    )
                ],
            )
        )
    column = {"at": audit_event.c.at, "kind": audit_event.c.kind, "actor_name": actor}[query.sort]
    order = (column.asc() if query.direction == "asc" else column.desc()).nulls_last()
    if query.from_at is not None:
        where.append(audit_event.c.at >= query.from_at)
    if query.to_at is not None:
        where.append(audit_event.c.at < query.to_at)
    return source, where, order


# Select and order existing immutable events without changing retention or opening a new authority.
class SqlAuditDirectory:
    # Runtime history reads require no audit UPDATE/DELETE/TRUNCATE or ownership privileges.
    def __init__(self, engine: Engine):
        self.engine = engine

    # Literal search and allowlisted sort identifiers cannot become SQL or select another workspace.
    def directory(self, workspace: str, query: AuditQuery):
        query = AuditQuery.model_validate(query)
        source, where, order = selection(workspace, query)
        with read_snapshot(self.engine) as connection:
            total = connection.scalar(select(func.count()).select_from(source).where(*where))
            pages = max(1, (total + query.page_size - 1) // query.page_size)
            page = min(query.page, pages)
            rows = (
                connection.execute(
                    select(audit_event, administrator.c.display_name.label("administrator_name"))
                    .select_from(source)
                    .where(*where)
                    .order_by(order, audit_event.c.id)
                    .offset((page - 1) * query.page_size)
                    .limit(query.page_size)
                )
                .mappings()
                .all()
            )
            resources = resource_context(connection, workspace, rows)
            return AuditDirectory(
                items=[
                    entry(row).model_copy(update={"resources": resources.get(row["id"], ())})
                    for row in rows
                ],
                total=total,
                page=page,
                page_size=query.page_size,
                pages=pages,
            )
