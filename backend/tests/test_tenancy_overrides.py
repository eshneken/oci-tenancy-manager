"""Override inheritance, immutable revision identity and staged-review admission invariants."""

import json
from contextlib import nullcontext
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_baseline_authoring import NOW, result
from test_configuration_updates import update_case

from otm.configuration.override_contracts import (
    CreateConfigurationPlan,
    OverrideContext,
    OverrideValues,
    SaveConfigurationReview,
    TenancyConfiguration,
    configuration_hash,
    effective_content,
)
from otm.configuration.plans import (
    ConfigurationPlans,
    accepted_plan,
    finish_plan,
    plan_row,
    reviewed_preview,
    target_rows,
)
from otm.configuration.revisions import (
    accept_configuration,
    configuration_is_verified,
    configuration_view,
    load_configuration,
    override_conflict,
)
from otm.configuration.rollout_contracts import (
    ConfigurationPlanView,
    ConfigurationPreview,
    ConfigurationUpdate,
)
from otm.operations.contracts import canonical_hash
from otm.storage.organization import OrganizationConflict

__all__ = ["update_case"]


# Build one explicit immutable snapshot from typed values without borrowing mutable provider state.
def revision(c, values=None, **changes):
    values = values or OverrideValues(monthly_budget_override_amount=Decimal("500"))
    return TenancyConfiguration(
        **values.model_dump(),
        id=uuid4(),
        tenancy_id=c.target.tenancy_id,
        baseline_version_id=c.baseline.id,
        revision_number=1,
        previous_id=None,
        operation_id=c.operation["id"],
        created_by=c.actor.actor.key,
        created_at=NOW,
        effective_hash=configuration_hash(c.baseline, values),
        **changes,
    )


# Every category is independent; clearing values inherits exact arrays without merging or deleting.
def test_override_resolution_and_hash_provenance(update_case):
    c = update_case
    inherited = effective_content(c.baseline, OverrideValues())
    assert inherited == c.baseline.content
    values = OverrideValues(
        policy_override_statements=("Allow explicit override",),
        monthly_budget_override_amount=Decimal("700"),
    )
    content = effective_content(c.baseline, values)
    assert content.policy_statements == values.policy_override_statements
    assert (
        content.quota_statements == inherited.quota_statements
        and content.tag_defaults == inherited.tag_defaults
    )
    assert content.monthly_budget_amount == 700
    assert configuration_hash(c.baseline, values) != configuration_hash(
        c.baseline, OverrideValues()
    )
    assert configuration_hash(c.baseline, values) != configuration_hash(
        c.baseline.model_copy(update={"id": uuid4()}), values
    )


# Malformed or unsupported replacement content cannot become an interpreted delete or expression.
@pytest.mark.parametrize(
    "data",
    [
        {"policy_override_statements": []},
        {"quota_override_statements": [" "]},
        {"policy_override_statements": ["x"] * 51},
        {"quota_override_statements": ["x" * 2001]},
        {"monthly_budget_override_amount": "0"},
        {"monthly_budget_override_amount": "250.5"},
        {"monthly_budget_override_amount": "10000000000000000"},
        {"policy_override_statements": ["-----BEGIN PRIVATE KEY-----"]},
        {"quota_override_statements": ["x\u0000"]},
        {"tag_defaults": []},
        {"budget_currency": "EUR"},
    ],
)
def test_invalid_override_values(data):
    with pytest.raises(ValueError):
        OverrideValues.model_validate_json(json.dumps(data))


# Accepted context is explicit; arbitrary fields and batch-shaped override commands are refused.
def test_override_command_modes(update_case):
    c = update_case
    context = OverrideContext(
        baseline_version_id=c.baseline.id, tenancy_revision=1, configuration_id=None
    )
    body = {
        "client_request_key": uuid4(),
        "preview_hash": "a" * 64,
        "override_mode": True,
        "overrides": OverrideValues(),
        "override_context": context,
        "tenancy_id": c.target.tenancy_id,
    }
    assert ConfigurationUpdate(**body).override_context == context
    for changes in (
        {"tenancy_id": None},
        {"plan_id": uuid4()},
        {"override_context": None},
        {"overrides": None},
        {"override_mode": False},
    ):
        with pytest.raises(ValueError):
            ConfigurationUpdate(**{**body, **changes})


# SQL round trips validate canonical effective evidence and same-workspace/same-tenancy lookups.
def test_configuration_storage_roundtrip_and_scope(update_case):
    c = update_case
    model = revision(c)
    raw = model.model_dump()
    assert configuration_view(raw, c.baseline) == model
    with pytest.raises(ValueError):
        configuration_view({**raw, "effective_hash": "0" * 64}, c.baseline)
    connection = Mock()
    connection.execute.return_value = result(raw)
    with patch("otm.configuration.revisions.published_baseline", return_value=c.baseline):
        assert (
            load_configuration(connection, c.policy.workspace_id, c.target.tenancy_id, model.id)
            == model
        )
    parameters = connection.execute.call_args.args[0].compile().params
    assert (
        c.policy.workspace_id in parameters.values() and c.target.tenancy_id in parameters.values()
    )
    assert load_configuration(connection, c.policy.workspace_id, c.target.tenancy_id, None) is None
    connection.execute.return_value = result(None)
    with pytest.raises(OrganizationConflict):
        load_configuration(connection, c.policy.workspace_id, c.target.tenancy_id, model.id)
    with patch("otm.configuration.revisions.load_configuration", return_value=model):
        new = accept_configuration(
            connection,
            c.policy.workspace_id,
            {"id": c.target.tenancy_id, "desired_configuration_id": model.id},
            c.baseline,
            OverrideValues(),
            uuid4(),
            c.actor.actor.key,
            NOW,
        )
    assert new.previous_id == model.id and new.revision_number == 2
    assert (
        configuration_is_verified(
            {
                **c.row,
                "baseline_version_id": c.baseline.id,
                "verified_baseline_version_id": c.baseline.id,
                "desired_configuration_id": new.id,
                "last_verified_configuration_id": model.id,
            },
            c.baseline,
        )
        is False
    )


# Only changed overridden statements require review; compatible budget overrides carry
# independently.
def test_conflict_categories_and_budget_meaning(update_case):
    c = update_case
    row = {**c.row, "baseline_version_id": c.baseline.id}
    next_content = c.baseline.content.model_copy(update={"policy_statements": ("New policy",)})
    latest = c.baseline.model_copy(update={"id": uuid4(), "content": next_content})
    with patch("otm.configuration.revisions.published_baseline", return_value=c.baseline):
        assert (
            override_conflict(
                c.connection,
                c.policy.workspace_id,
                row,
                latest,
                OverrideValues(monthly_budget_override_amount=Decimal("900")),
            )
            is None
        )
        conflict = override_conflict(
            c.connection,
            c.policy.workspace_id,
            row,
            latest,
            OverrideValues(policy_override_statements=("Old override",)),
        )
        assert conflict.policy_review and not conflict.quota_review
        with pytest.raises(OrganizationConflict):
            override_conflict(
                c.connection,
                c.policy.workspace_id,
                row,
                latest.model_copy(
                    update={"content": next_content.model_copy(update={"budget_currency": "EUR"})}
                ),
                OverrideValues(monthly_budget_override_amount=Decimal("900")),
            )
    assert (
        override_conflict(c.connection, c.policy.workspace_id, c.row, latest, OverrideValues())
        is None
    )


# Snapshot integrity is checked before a mutable review choice is trusted or displayed.
def test_plan_target_hash_and_owner_scope(update_case):
    c = update_case
    connection = Mock()
    connection.execute.return_value = result(None)
    with pytest.raises(OrganizationConflict):
        plan_row(connection, c.policy.workspace_id, c.actor.actor.key, uuid4())
    raw = {
        "tenancy_id": c.target.tenancy_id,
        "proposal": c.target.model_dump(mode="json"),
        "proposal_hash": canonical_hash(c.target.model_dump(mode="json")),
    }
    connection.execute.return_value = result([raw])
    assert target_rows(connection, c.policy.workspace_id, uuid4()) == [raw]
    connection.execute.return_value = result([{**raw, "proposal_hash": "0" * 64}])
    with pytest.raises(ValueError):
        target_rows(connection, c.policy.workspace_id, uuid4())
    connection.execute.return_value = result([{**raw, "tenancy_id": uuid4()}])
    with pytest.raises(ValueError):
        target_rows(connection, c.policy.workspace_id, uuid4())


# Model a reviewed target with independent policy/quota choices and immutable source context.
def staged(c, policy_choice="use_new_baseline", quota_choice="keep_override"):
    from otm.configuration.override_contracts import OverrideConflict

    values = OverrideValues(
        policy_override_statements=("Old policy override",),
        quota_override_statements=("Old quota override",),
        monthly_budget_override_amount=Decimal("500"),
    )
    target = c.target.model_copy(update={"overrides": values})
    proof = {
        "tenancy_id": target.tenancy_id,
        "proposal": target.model_dump(mode="json"),
        "proposal_hash": canonical_hash(target.model_dump(mode="json")),
        "policy_choice": policy_choice,
        "quota_choice": quota_choice,
        "reviewed_by": c.actor.actor.key,
        "reviewed_at": NOW,
    }
    row = {
        "id": uuid4(),
        "revision": 1,
        "scope_tenancy_id": None,
        "target_baseline_version_id": c.baseline.id,
        "candidate_set_hash": "a" * 64,
        "operation_id": None,
    }
    conflict = OverrideConflict(
        tenancy_id=target.tenancy_id,
        tenancy_name=target.name,
        old_baseline=c.baseline,
        overrides=values,
        policy_review=True,
        quota_review=True,
    )
    from otm.configuration.rollout_contracts import ConfigurationBlocker

    preview = ConfigurationPreview(
        baseline=c.baseline,
        tenancy_id=None,
        ready_count=0,
        pending_count=0,
        blockers=(
            ConfigurationBlocker(
                tenancy_id=target.tenancy_id, name=target.name, code="OVERRIDE_REVIEW_REQUIRED"
            ),
        ),
        conflicts=(conflict,),
        preview_hash="a" * 64,
    )
    return row, proof, preview, target


# Reviewed choices affect only prospective full-list values; acceptance is still a separate gate.
@pytest.mark.parametrize("complete", [False, True])
def test_review_resolution_and_stale_plan_never_rebase(update_case, complete):
    c = update_case
    row, proof, preview, target = staged(c, quota_choice="keep_override" if complete else None)
    with (
        patch.object(c.service, "_preview", return_value=(preview, (target,))),
        patch("otm.configuration.plans.target_rows", return_value=[proof]),
    ):
        view, targets = reviewed_preview(
            c.service, c.connection, c.policy.workspace_id, c.actor, row
        )
    assert view.state == "draft" and view.preview.ready_count == int(complete)
    if complete:
        assert targets[0].overrides.policy_override_statements is None
        assert (
            targets[0].overrides.quota_override_statements
            == target.overrides.quota_override_statements
        )
        assert (
            targets[0].overrides.monthly_budget_override_amount == 500
            and targets[0].review.plan_id == row["id"]
        )
    else:
        assert targets[0].overrides == target.overrides
    with (
        patch.object(
            c.service,
            "_preview",
            return_value=(
                preview.model_copy(
                    update={
                        "baseline": c.baseline.model_copy(update={"id": uuid4()}),
                        "preview_hash": "b" * 64,
                    }
                ),
                (target,),
            ),
        ),
        patch("otm.configuration.plans.target_rows", return_value=[proof]),
        patch("otm.configuration.plans.published_baseline", return_value=c.baseline),
    ):
        stale, _ = reviewed_preview(c.service, c.connection, c.policy.workspace_id, c.actor, row)
    assert (
        stale.state == "stale"
        and stale.preview.baseline.id == c.baseline.id
        and stale.preview.ready_count == 0
    )
    with (
        patch("otm.configuration.plans.plan_row", return_value=row),
        patch("otm.configuration.plans.reviewed_preview", return_value=(stale, (target,))),
    ):
        with pytest.raises(OrganizationConflict):
            accepted_plan(c.service, c.connection, c.policy.workspace_id, c.actor, row["id"])
    finish_plan(
        c.connection,
        c.policy.workspace_id,
        row["id"],
        c.operation["id"],
        (target.model_copy(update={"configuration": revision(c)}),),
        NOW,
    )
    statements = [call.args[0] for call in c.connection.execute.call_args_list[-2:]]
    assert [statement.table.name for statement in statements] == [
        "otm_configuration_plan_target",
        "otm_configuration_plan",
    ]


# Plan creation/replay, optimistic reviews and read authority reuse the existing store boundary.
def test_plan_service_commands_and_staged_audit(update_case):
    c = update_case
    row, proof, preview, target = staged(c)
    app = ConfigurationPlans(c.service)
    view = ConfigurationPlanView(id=row["id"], revision=1, state="draft", preview=preview)
    create = CreateConfigurationPlan(client_request_key=uuid4())
    c.connection.execute.return_value = result(None)
    with (
        patch.object(c.service, "_preview", return_value=(preview, (target,))),
        patch("otm.configuration.plans.plan_row", return_value=row),
        patch("otm.configuration.plans.reviewed_preview", return_value=(view, (target,))),
    ):
        assert app.create(c.actor, create) == view
    c.connection.execute.return_value = result({**row, "scope_tenancy_id": None})
    with patch("otm.configuration.plans.reviewed_preview", return_value=(view, (target,))):
        assert app.create(c.actor, create) == view
        with pytest.raises(OrganizationConflict):
            app.create(c.actor, create.model_copy(update={"tenancy_id": uuid4()}))
    with (
        patch("otm.configuration.plans.read_snapshot", return_value=nullcontext(c.connection)),
        patch("otm.configuration.plans.plan_row", return_value=row),
        patch("otm.configuration.plans.reviewed_preview", return_value=(view, (target,))),
    ):
        assert app.read(c.actor, row["id"]) == view
    command = SaveConfigurationReview(
        expected_revision=1,
        tenancy_id=target.tenancy_id,
        policy_choice="keep_override",
        quota_choice="use_new_baseline",
    )
    c.connection.execute.return_value = Mock(rowcount=1)
    with (
        patch("otm.configuration.plans.plan_row", return_value=row),
        patch("otm.configuration.plans.reviewed_preview", return_value=(view, (target,))),
        patch("otm.configuration.plans.target_rows", return_value=[proof]),
    ):
        assert app.review(c.actor, row["id"], command) == view
        with pytest.raises(OrganizationConflict):
            app.review(c.actor, row["id"], command.model_copy(update={"expected_revision": 2}))
        with pytest.raises(OrganizationConflict):
            app.review(c.actor, row["id"], command.model_copy(update={"quota_choice": None}))
    inserts = [
        call.args[0].compile().params
        for call in c.connection.execute.call_args_list
        if getattr(call.args[0], "is_insert", False) and call.args[0].table.name == "audit_event"
    ]
    assert inserts[-1]["kind"] == "configuration_review_staged" and inserts[-1]["data"][
        "plan_id"
    ] == str(row["id"])
