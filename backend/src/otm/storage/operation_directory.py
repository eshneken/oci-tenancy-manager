"""Workspace-scoped, read-only views over existing operation, intent and step authorities."""

import json
from datetime import UTC
from uuid import UUID

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.engine import Engine

from otm.configuration.drift_contracts import ConfigurationCheckEvidence
from otm.configuration.rollout_contracts import ConfigurationOutcome, ConfigurationRetryEvidence
from otm.financial.contracts import CostEvidence
from otm.notifications.contracts import NotificationEvidence
from otm.notifications.service import list_for_operation
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.operations.execution_contracts import InspectionOutcome
from otm.operations.responsibility import ResponsibilityEvidence, eligible, execution_authority
from otm.operations.views import (
    OperationDetail,
    OperationDirectory,
    OperationEventView,
    OperationQuery,
    OperationStepView,
    OperationSummary,
)
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import (
    administrator,
    audit_event,
    operation,
    operation_step,
    org_person,
    tenancy,
)
from otm.tenancies.contracts import OrganizationActionOutcome
from otm.tenancies.labels import ACTION_LABELS
from otm.tenancies.onboarding_contracts import OnboardingEvidence


# Convert stored timestamps to UTC without substituting a retrieval time for missing evidence.
def utc(value):
    return value.astimezone(UTC) if value is not None else None


# Read existing authorities without starting jobs, changing status or touching provider credentials.
class SqlOperationDirectory:
    # Use the explicitly injected restricted application engine; construction opens no connection.
    def __init__(self, engine: Engine):
        self.engine = engine

    # Concurrent workers cannot mix an old operation with newer steps or count/page results.
    def snapshot(self):
        return read_snapshot(self.engine)

    # Follow the exact committed intent pointer, including workspace and positive revision.
    def joined(self):
        return operation.join(
            audit_event,
            and_(
                audit_event.c.workspace_id == operation.c.workspace_id,
                audit_event.c.operation_id == operation.c.id,
                audit_event.c.id == operation.c.current_intent_event_id,
                audit_event.c.intent_revision == operation.c.current_intent_revision,
                audit_event.c.kind == "operation_intent",
            ),
        )

    # Select public-source data explicitly; response models never serialize a whole database row.
    def selection(self):
        return select(
            operation,
            audit_event.c.data.label("intent_data"),
            audit_event.c.data_hash.label("intent_hash"),
            tenancy.c.id.label("registered_tenancy_id"),
        ).select_from(
            self.joined().outerjoin(
                tenancy,
                and_(
                    tenancy.c.workspace_id == operation.c.workspace_id,
                    tenancy.c.tenancy_ocid
                    == audit_event.c.data["intent"]["target"]["tenancy_ocid"].astext,
                ),
            )
        )

    # Reject malformed or mismatched immutable data instead of displaying a misleading OCI target.
    def summary(self, row):
        frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
        if (
            canonical_hash(row["intent_data"]) != row["intent_hash"]
            or frozen.intent.workspace_id != row["workspace_id"]
            or frozen.actor.key != row["initiating_actor_subject"]
        ):
            raise ValueError("INVALID_OPERATION_EVIDENCE")
        return OperationSummary(
            id=row["id"],
            kind=row["kind"],
            state=row["state"],
            stage=row["stage"],
            accepted_at=utc(row["accepted_at"]),
            updated_at=utc(row["updated_at"]),
            completed_at=utc(row["completed_at"]),
            initiated_by=frozen.actor.display_name,
            result_tenancy_id=row.get("registered_tenancy_id")
            if row["state"] == "succeeded"
            and frozen.intent.kind
            in {
                "organization_action",
                "configuration_update",
                "configuration_check",
                "cost_collection",
            }
            else None,
            guided_onboarding=frozen.intent.kind == "organization_action"
            and frozen.intent.onboarding_version in {1, 2, 3},
            target_tenancy_ocid=frozen.intent.target.tenancy_ocid,
            title=ACTION_LABELS[frozen.intent.action]
            if frozen.intent.kind == "organization_action"
            else "Refresh current month costs"
            if frozen.intent.kind == "cost_collection"
            else "Check configuration"
            if frozen.intent.kind == "configuration_check"
            else "Update tenancy overrides"
            if frozen.intent.kind == "configuration_update"
            and frozen.intent.change_kind == "override_change"
            else "Repair assigned configuration"
            if frozen.intent.kind == "configuration_update"
            and frozen.intent.change_kind == "repair"
            else f"Update baseline v{frozen.intent.baseline.version_number}"
            if frozen.intent.kind == "configuration_update"
            else None,
            target_label=frozen.intent.target.display_name
            if frozen.intent.kind
            in {
                "organization_action",
                "configuration_update",
                "configuration_check",
                "cost_collection",
            }
            else None,
        )

    # Count supported human work, not every blocked diagnostic; this never authorizes a command.
    def actionable(self):
        pending = (
            select(1)
            .where(
                org_person.c.workspace_id == operation.c.workspace_id,
                org_person.c.pending_operation_id == operation.c.id,
                cast(org_person.c.id, String)
                == audit_event.c.data["intent"]["target"]["person_id"].astext,
            )
            .correlate(operation, audit_event)
            .exists()
        )
        guided = and_(
            audit_event.c.data["intent"]["onboarding_version"].astext.in_(("1", "2", "3")),
            or_(
                operation.c.state == "needs_attention",
                operation.c.wait_reason.in_(("onboarding_handoff", "onboarding_review")),
            ),
        )
        return and_(
            operation.c.kind == "organization_action",
            audit_event.c.data["intent"]["kind"].astext == "organization_action",
            operation.c.state.in_(("waiting", "needs_attention")),
            pending,
            or_(guided, operation.c.effect_knowledge == "none"),
        )

    # SQL identifiers come from an allowlist; literal search never interprets %, _ or SQL syntax.
    def directory(self, workspace: str, query: OperationQuery):
        query = OperationQuery.model_validate(query)
        where = [operation.c.workspace_id == workspace]
        if query.state:
            where.append(operation.c.state == query.state)
        if query.query:
            target = audit_event.c.data["intent"]["target"]["tenancy_ocid"].astext
            where.append(
                or_(
                    target.icontains(query.query, autoescape=True),
                    cast(operation.c.id, String).icontains(query.query, autoescape=True),
                )
            )
        column = {
            name: operation.c[name] for name in ("accepted_at", "updated_at", "state", "stage")
        }[query.sort]
        order = column.asc() if query.direction == "asc" else column.desc()
        with self.snapshot() as connection:
            # Supported action count remains workspace-wide, independent of list filters.
            attention = connection.scalar(
                select(func.count())
                .select_from(self.joined())
                .where(
                    operation.c.workspace_id == workspace,
                    self.actionable(),
                )
            )
            total = connection.scalar(select(func.count()).select_from(self.joined()).where(*where))
            pages = max(1, (total + query.page_size - 1) // query.page_size)
            page = min(query.page, pages)
            rows = (
                connection.execute(
                    self.selection()
                    .where(*where)
                    .order_by(order, operation.c.id)
                    .offset((page - 1) * query.page_size)
                    .limit(query.page_size)
                )
                .mappings()
                .all()
            )
            return OperationDirectory(
                attention_count=attention,
                items=[self.summary(row) for row in rows],
                total=total,
                page=page,
                page_size=query.page_size,
                pages=pages,
            )

    # Return the same not-found result for an absent ID and an ID in another workspace.
    def detail(self, workspace: str, identifier: UUID, actor_subject=None):
        with self.snapshot() as connection:
            row = (
                connection.execute(
                    self.selection().where(
                        operation.c.workspace_id == workspace, operation.c.id == identifier
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            summary = self.summary(row)
            frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
            if summary.guided_onboarding:
                authority_id, _, authority_actor = execution_authority(connection, row, frozen)
                grant = (
                    connection.execute(
                        select(administrator).where(
                            administrator.c.workspace_id == workspace,
                            administrator.c.id == authority_id,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                summary = summary.model_copy(
                    update={
                        "responsible_administrator_id": authority_id,
                        "responsible_administrator_name": grant["display_name"]
                        if grant
                        else authority_actor.display_name,
                        "responsibility_revision": row["revision"],
                        "can_take_responsibility": bool(
                            actor_subject
                            and eligible(row, frozen.intent)
                            and row["responsible_actor_subject"] != actor_subject
                        ),
                    }
                )
            steps = (
                connection.execute(
                    select(operation_step)
                    .where(
                        operation_step.c.workspace_id == workspace,
                        operation_step.c.operation_id == identifier,
                        operation_step.c.intent_revision == row["current_intent_revision"],
                    )
                    .order_by(operation_step.c.step_key)
                )
                .mappings()
                .all()
            )
            events = (
                connection.execute(
                    select(
                        audit_event.c.kind,
                        audit_event.c.at,
                        audit_event.c.data,
                        audit_event.c.data_hash,
                    )
                    .where(
                        audit_event.c.workspace_id == workspace,
                        audit_event.c.operation_id == identifier,
                    )
                    .order_by(audit_event.c.at.desc(), audit_event.c.id.desc())
                    .limit(51)
                )
                .mappings()
                .all()
            )
            return OperationDetail(
                notifications=list_for_operation(connection, workspace, identifier),
                operation=summary,
                steps=[self.step(step) for step in steps],
                events=[self.event(event) for event in events[:50]],
                events_limited=len(events) > 50,
            )

    # Validate versioned outcomes before choosing a safe code; unknown results remain unknown.
    def step(self, row):
        outcome = (
            (
                CostEvidence
                if row["command_kind"] == "cost_collection"
                else ConfigurationCheckEvidence
                if row["command_kind"] == "configuration_check"
                else ConfigurationOutcome
                if row["command_kind"] == "configuration_update"
                else OnboardingEvidence
                if row["command_kind"] == "onboarding"
                else OrganizationActionOutcome
                if row["command_kind"] == "organization_action"
                else InspectionOutcome
            ).model_validate_json(json.dumps(row["last_outcome"]))
            if row["last_outcome"] is not None
            else None
        )
        return OperationStepView(
            step_key=row["step_key"],
            state=row["state"],
            attempt_number=row["attempt_number"],
            verified_at=utc(row["verified_at"]),
            safe_code=outcome.safe_code if outcome else None,
        )

    # Expose closed outcome codes only; immutable JSON itself stays private.
    def event(self, row):
        if canonical_hash(row["data"]) != row["data_hash"]:
            raise ValueError("INVALID_OPERATION_EVIDENCE")
        if row["kind"] == "email_delivery":
            NotificationEvidence.model_validate_json(json.dumps(row["data"]))
        if row["kind"] == "operation_responsibility_changed":
            ResponsibilityEvidence.model_validate_json(json.dumps(row["data"]))
        outcome = (
            (
                CostEvidence
                if row["kind"] == "cost_collection_outcome"
                else ConfigurationCheckEvidence
                if row["kind"] == "configuration_check_outcome"
                else ConfigurationOutcome
                if row["kind"] == "configuration_outcome"
                else ConfigurationRetryEvidence
                if row["kind"] == "configuration_retry"
                else OnboardingEvidence
                if row["kind"] in {"onboarding_action", "onboarding_outcome"}
                else OrganizationActionOutcome
                if row["kind"] == "organization_action_outcome"
                else InspectionOutcome
            ).model_validate_json(json.dumps(row["data"]))
            if row["kind"]
            in {
                "inspection_outcome",
                "configuration_outcome",
                "configuration_check_outcome",
                "cost_collection_outcome",
                "configuration_retry",
                "organization_action_outcome",
                "onboarding_action",
                "onboarding_outcome",
            }
            else None
        )
        return OperationEventView(
            kind=row["kind"], at=utc(row["at"]), safe_code=outcome.safe_code if outcome else None
        )
