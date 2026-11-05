"""Persist review choices; accept the whole exact batch atomically."""

import json
from uuid import uuid4

from sqlalchemy import select, update

from otm.configuration.override_contracts import ConfigurationReviewEvidence, OverrideReviewEvidence
from otm.configuration.rollout_contracts import ConfigurationPlanView, ConfigurationTarget
from otm.configuration.service import published_baseline
from otm.operations.contracts import canonical_hash
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import audit_event, configuration_plan, configuration_plan_target


# A missing or another administrator's plan has the same not-found result.
def plan_row(connection, workspace, actor, identifier):
    row = (
        connection.execute(
            select(configuration_plan).where(
                configuration_plan.c.workspace_id == workspace,
                configuration_plan.c.created_by == actor,
                configuration_plan.c.id == identifier,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
    return row


# Verify every persisted candidate snapshot before it can contribute a staged choice or approval.
def target_rows(connection, workspace, identifier):
    rows = (
        connection.execute(
            select(configuration_plan_target)
            .where(
                configuration_plan_target.c.workspace_id == workspace,
                configuration_plan_target.c.plan_id == identifier,
            )
            .order_by(configuration_plan_target.c.tenancy_id)
        )
        .mappings()
        .all()
    )
    for row in rows:
        if canonical_hash(row["proposal"]) != row["proposal_hash"]:
            raise ValueError("INVALID_PLAN_EVIDENCE")
        target = ConfigurationTarget.model_validate_json(json.dumps(row["proposal"]))
        if target.tenancy_id != row["tenancy_id"]:
            raise ValueError("INVALID_PLAN_SCOPE")
    return rows


# Choices change only staged override columns; no baseline statement is silently appended or merged.
def reviewed_preview(service, connection, workspace, principal, row):
    preview, targets = service._preview(connection, workspace, row["scope_tenancy_id"])
    rows = target_rows(connection, workspace, row["id"])
    fresh = preview.preview_hash == row["candidate_set_hash"] and {
        t.tenancy_id for t in targets
    } == {r["tenancy_id"] for r in rows}
    if not fresh:
        # A stale or accepted plan keeps its original publication; refresh is an explicit new plan.
        frozen = (
            published_baseline(connection, workspace, row["target_baseline_version_id"])
            if row["target_baseline_version_id"]
            else None
        )
        preview = preview.model_copy(
            update={
                "baseline": frozen,
                "conflicts": (),
                "blockers": (),
                "ready_count": 0,
                "pending_count": 0,
            }
        )
        targets = tuple(
            ConfigurationTarget.model_validate_json(json.dumps(r["proposal"])) for r in rows
        )
    staged = {r["tenancy_id"]: r for r in rows}
    conflicts = []
    resolved = set()
    accepted = []
    for conflict in preview.conflicts:
        decision = staged.get(conflict.tenancy_id)
        if decision:
            conflict = conflict.model_copy(
                update={
                    "policy_choice": decision["policy_choice"],
                    "quota_choice": decision["quota_choice"],
                }
            )
            if (not conflict.policy_review or conflict.policy_choice) and (
                not conflict.quota_review or conflict.quota_choice
            ):
                resolved.add(conflict.tenancy_id)
        conflicts.append(conflict)
    for target in targets:
        choice = staged.get(target.tenancy_id)
        values = target.overrides
        review = None
        if choice and target.tenancy_id in resolved:
            changes = {}
            if choice["policy_choice"] == "use_new_baseline":
                changes["policy_override_statements"] = None
            if choice["quota_choice"] == "use_new_baseline":
                changes["quota_override_statements"] = None
            values = values.model_copy(update=changes)
            review = OverrideReviewEvidence(
                plan_id=row["id"],
                policy_choice=choice["policy_choice"],
                quota_choice=choice["quota_choice"],
                reviewed_by=choice["reviewed_by"],
                reviewed_at=choice["reviewed_at"],
            )
        accepted.append(target.model_copy(update={"overrides": values, "review": review}))
    blockers = tuple(
        b
        for b in preview.blockers
        if not (b.code == "OVERRIDE_REVIEW_REQUIRED" and b.tenancy_id in resolved)
    )
    digest = canonical_hash(
        {
            "plan_id": str(row["id"]),
            "revision": row["revision"],
            "source": row["candidate_set_hash"],
            "choices": [
                {
                    "tenancy_id": str(r["tenancy_id"]),
                    "policy": r["policy_choice"],
                    "quota": r["quota_choice"],
                    "by": r["reviewed_by"],
                    "at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
                }
                for r in rows
            ],
        }
    )
    view = ConfigurationPlanView(
        id=row["id"],
        revision=row["revision"],
        state="accepted" if row["operation_id"] else "draft" if fresh else "stale",
        operation_id=row["operation_id"],
        preview=preview.model_copy(
            update={
                "conflicts": tuple(conflicts),
                "blockers": blockers,
                "ready_count": len(targets) - len(blockers) if fresh else 0,
                "preview_hash": digest,
            }
        ),
    )
    return view, tuple(accepted)


# Final acceptance rechecks source hashes and every unresolved blocker under the workspace lock.
def accepted_plan(service, connection, workspace, principal, identifier):
    row = plan_row(connection, workspace, principal.actor.key, identifier)
    view, targets = reviewed_preview(service, connection, workspace, principal, row)
    if view.state != "draft":
        raise OrganizationConflict("CONFIGURATION_PREVIEW_CHANGED")
    return view.preview, targets


# Attach all accepted revision IDs only after the same transaction has frozen operation/target
# intent.
def finish_plan(connection, workspace, identifier, operation, targets, at):
    for target in targets:
        connection.execute(
            update(configuration_plan_target)
            .where(
                configuration_plan_target.c.workspace_id == workspace,
                configuration_plan_target.c.plan_id == identifier,
                configuration_plan_target.c.tenancy_id == target.tenancy_id,
            )
            .values(accepted_configuration_id=target.configuration.id)
        )
    connection.execute(
        update(configuration_plan)
        .where(
            configuration_plan.c.workspace_id == workspace,
            configuration_plan.c.id == identifier,
            configuration_plan.c.operation_id.is_(None),
        )
        .values(operation_id=operation, updated_at=at)
    )


# Local plan commands reuse the current administrator/workspace transaction authority and queue
# owner.
class ConfigurationPlans:
    # Keep admission in the existing rollout service rather than introducing another coordinator.
    def __init__(self, rollouts):
        self.rollouts = rollouts
        self.store = rollouts.store

    # Creating a draft persists exact candidate snapshots but no desires, reservations or
    # native jobs.
    def create(self, principal, command):
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            old = (
                connection.execute(
                    select(configuration_plan).where(
                        configuration_plan.c.workspace_id == workspace,
                        configuration_plan.c.created_by == principal.actor.key,
                        configuration_plan.c.client_request_key == command.client_request_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if old:
                if old["scope_tenancy_id"] != command.tenancy_id:
                    raise OrganizationConflict("CONFIGURATION_PREVIEW_CHANGED")
                return reviewed_preview(self.rollouts, connection, workspace, principal, old)[0]
            preview, targets = self.rollouts._preview(connection, workspace, command.tenancy_id)
            identifier = uuid4()
            connection.execute(
                configuration_plan.insert().values(
                    id=identifier,
                    workspace_id=workspace,
                    scope_tenancy_id=command.tenancy_id,
                    target_baseline_version_id=preview.baseline.id if preview.baseline else None,
                    candidate_set_hash=preview.preview_hash,
                    client_request_key=command.client_request_key,
                    revision=1,
                    created_by=principal.actor.key,
                    created_at=at,
                    updated_at=at,
                )
            )
            for target in targets:
                payload = target.model_dump(mode="json")
                connection.execute(
                    configuration_plan_target.insert().values(
                        workspace_id=workspace,
                        plan_id=identifier,
                        tenancy_id=target.tenancy_id,
                        proposal=payload,
                        proposal_hash=canonical_hash(payload),
                    )
                )
            row = plan_row(connection, workspace, principal.actor.key, identifier)
            return reviewed_preview(self.rollouts, connection, workspace, principal, row)[0]

    # Reloading reveals stale/accepted status rather than silently rebuilding a reviewed target set.
    def read(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            row = plan_row(connection, workspace, principal.actor.key, identifier)
            return reviewed_preview(self.rollouts, connection, workspace, principal, row)[0]

    # Save exactly the required full-list choices with immutable actor/time evidence;
    # nothing applies.
    def review(self, principal, identifier, command):
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            row = plan_row(connection, workspace, principal.actor.key, identifier)
            view, _ = reviewed_preview(self.rollouts, connection, workspace, principal, row)
            if view.state != "draft" or row["revision"] != command.expected_revision:
                raise OrganizationConflict("CONFIGURATION_PREVIEW_CHANGED")
            conflict = next(
                (c for c in view.preview.conflicts if c.tenancy_id == command.tenancy_id), None
            )
            if (
                conflict is None
                or bool(command.policy_choice) != conflict.policy_review
                or bool(command.quota_choice) != conflict.quota_review
            ):
                raise OrganizationConflict("CONFIGURATION_UPDATE_BLOCKED")
            proof = next(
                r
                for r in target_rows(connection, workspace, identifier)
                if r["tenancy_id"] == command.tenancy_id
            )
            connection.execute(
                update(configuration_plan_target)
                .where(
                    configuration_plan_target.c.workspace_id == workspace,
                    configuration_plan_target.c.plan_id == identifier,
                    configuration_plan_target.c.tenancy_id == command.tenancy_id,
                )
                .values(
                    policy_choice=command.policy_choice,
                    quota_choice=command.quota_choice,
                    reviewed_by=principal.actor.key,
                    reviewed_at=at,
                )
            )
            connection.execute(
                update(configuration_plan)
                .where(
                    configuration_plan.c.workspace_id == workspace,
                    configuration_plan.c.id == identifier,
                )
                .values(revision=row["revision"] + 1, updated_at=at)
            )
            payload = ConfigurationReviewEvidence(
                plan_id=identifier,
                tenancy_id=command.tenancy_id,
                baseline_id=view.preview.baseline.id,
                proposal_hash=proof["proposal_hash"],
                policy_choice=command.policy_choice,
                quota_choice=command.quota_choice,
            ).model_dump(mode="json")
            connection.execute(
                audit_event.insert().values(
                    id=uuid4(),
                    workspace_id=workspace,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="configuration_review_staged",
                    at=at,
                    contract_version="configuration-review-1",
                    data=payload,
                    data_hash=canonical_hash(payload),
                )
            )
            return reviewed_preview(
                self.rollouts,
                connection,
                workspace,
                principal,
                plan_row(connection, workspace, principal.actor.key, identifier),
            )[0]
