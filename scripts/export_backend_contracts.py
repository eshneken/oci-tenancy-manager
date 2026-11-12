"""Generate implemented application schemas from authoritative production models."""

import argparse
import json
from pathlib import Path

from otm.audit.contracts import AuditDirectory, AuditExportQuery, AuditQuery
from otm.auth.administrators import (
    AdministratorChange,
    AdministratorDirectory,
    AdministratorQuery,
    AdministratorRevoked,
)
from otm.auth.contracts import SessionView
from otm.auth.local import LocalSignIn, SecurityEvidence
from otm.configuration.contracts import (
    BaselineDirectory,
    BaselineDraft,
    BaselineQuery,
    BaselineVersion,
    PublishBaseline,
    SaveBaselineDraft,
)
from otm.configuration.drift_contracts import (
    ConfigurationCheckRequest,
    ConfigurationCheckSummary,
    ConfigurationDriftDirectory,
    ConfigurationDriftQuery,
)
from otm.configuration.override_contracts import (
    CreateConfigurationPlan,
    OverrideEditor,
    OverridePreviewRequest,
    SaveConfigurationReview,
)
from otm.configuration.repair_contracts import ConfigurationRepairRequest
from otm.configuration.rollout_contracts import (
    ConfigurationPlanView,
    ConfigurationPreview,
    ConfigurationProgress,
    ConfigurationUpdate,
)
from otm.email_policy import EmailContacts, EmailPolicyView, EmailRoute
from otm.financial.contracts import (
    BudgetReadResult,
    CostRefreshReceipt,
    CostRefreshRequest,
    CostView,
)
from otm.notifications.contracts import NotificationSummary
from otm.operations.contracts import Acceptance, InspectImportRequest, IntentEventData
from otm.operations.execution_contracts import DispatchEvent, InspectionOutcome
from otm.operations.responsibility import ResponsibilityCommand
from otm.operations.sandbox import InspectionSubmission, SandboxCatalog, SandboxConfig
from otm.operations.views import OperationDetail, OperationDirectory, OperationQuery
from otm.organization.mapping_contracts import (
    MappingApply,
    MappingPreview,
    MappingRequest,
    MappingSettings,
)
from otm.organization.persistence_contracts import (
    OrganizationEvidence,
    OrganizationOutcome,
)
from otm.organization.views import OrganizationDirectory, OrganizationQuery
from otm.providers.inspection_contracts import RESULT_ADAPTER, InspectTenancy
from otm.settings import ApplicationSettings, BrandingView
from otm.tenancies.contracts import ActionReceipt, OrganizationAction
from otm.tenancies.deletion import TenancyDeletionCommand, TenancyDeletionPreview
from otm.tenancies.onboarding_contracts import OnboardingCommand, OnboardingView
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.recovery_network_contracts import (
    RecoveryNetworkPreview,
    RecoveryNetworkRequest,
)
from otm.tenancies.recovery_password_contracts import (
    RecoveryPasswordDisclosure,
    RecoveryPasswordRequest,
    RecoveryPasswordView,
)
from otm.tenancies.refresh_contracts import (
    FleetRefreshReceipt,
    FleetRefreshRequest,
    FleetRefreshStatus,
    FleetRefreshStatusRequest,
)
from otm.tenancies.required_users import RequiredUsersDirectory
from otm.tenancies.signing_key_contracts import SigningKeyRequest, SigningKeyView
from otm.tenancies.views import (
    PersonWorkflow,
    ReviewDirectory,
    ReviewQuery,
    TenancyDetail,
    TenancyDirectory,
    TenancyQuery,
)

ROOT = Path(__file__).resolve().parents[1]


# Export implemented auth, history, branding and operation contracts, not design-only APIs.
def contracts() -> dict[str, dict]:
    return {
        "recovery-password-view.schema.json": RecoveryPasswordView.model_json_schema(),
        "recovery-password-request.schema.json": RecoveryPasswordRequest.model_json_schema(),
        "recovery-password-disclosure.schema.json": RecoveryPasswordDisclosure.model_json_schema(),
        "recovery-network-preview.schema.json": RecoveryNetworkPreview.model_json_schema(),
        "recovery-network-request.schema.json": RecoveryNetworkRequest.model_json_schema(),
        "cost-refresh-request.schema.json": CostRefreshRequest.model_json_schema(),
        "cost-refresh-receipt.schema.json": CostRefreshReceipt.model_json_schema(),
        "cost-view.schema.json": CostView.model_json_schema(),
        "budget-read-result.schema.json": BudgetReadResult.model_json_schema(),
        "email-policy-view.schema.json": EmailPolicyView.model_json_schema(),
        "email-contacts.schema.json": EmailContacts.model_json_schema(),
        "email-route.schema.json": EmailRoute.model_json_schema(),
        "notification-summary.schema.json": NotificationSummary.model_json_schema(),
        "responsibility-command.schema.json": ResponsibilityCommand.model_json_schema(),
        "configuration-drift-directory.schema.json": (
            ConfigurationDriftDirectory.model_json_schema()
        ),
        "configuration-drift-query.schema.json": ConfigurationDriftQuery.model_json_schema(),
        "configuration-check-detail.schema.json": ConfigurationCheckSummary.model_json_schema(),
        "configuration-check-request.schema.json": ConfigurationCheckRequest.model_json_schema(),
        "override-editor.schema.json": OverrideEditor.model_json_schema(),
        "override-preview-request.schema.json": OverridePreviewRequest.model_json_schema(),
        "configuration-plan.schema.json": ConfigurationPlanView.model_json_schema(),
        "configuration-plan-create.schema.json": CreateConfigurationPlan.model_json_schema(),
        "configuration-plan-review.schema.json": SaveConfigurationReview.model_json_schema(),
        "configuration-preview.schema.json": ConfigurationPreview.model_json_schema(),
        "configuration-repair-request.schema.json": ConfigurationRepairRequest.model_json_schema(),
        "configuration-update.schema.json": ConfigurationUpdate.model_json_schema(),
        "configuration-progress.schema.json": ConfigurationProgress.model_json_schema(),
        "baseline-version.schema.json": BaselineVersion.model_json_schema(),
        "baseline-query.schema.json": BaselineQuery.model_json_schema(),
        "baseline-publish.schema.json": PublishBaseline.model_json_schema(),
        "baseline-directory.schema.json": BaselineDirectory.model_json_schema(),
        "baseline-draft.schema.json": BaselineDraft.model_json_schema(),
        "baseline-save.schema.json": SaveBaselineDraft.model_json_schema(),
        "mapping-settings.schema.json": MappingSettings.model_json_schema(),
        "mapping-request.schema.json": MappingRequest.model_json_schema(),
        "mapping-apply.schema.json": MappingApply.model_json_schema(),
        "mapping-preview.schema.json": MappingPreview.model_json_schema(),
        "tenancy-deletion-command.schema.json": TenancyDeletionCommand.model_json_schema(),
        "tenancy-deletion-preview.schema.json": TenancyDeletionPreview.model_json_schema(),
        "onboarding-command.schema.json": OnboardingCommand.model_json_schema(),
        "onboarding-view.schema.json": OnboardingView.model_json_schema(),
        "organization-action.schema.json": OrganizationAction.model_json_schema(),
        "organization-action-receipt.schema.json": ActionReceipt.model_json_schema(),
        "organization-person-workflow.schema.json": PersonWorkflow.model_json_schema(),
        "organization-review-directory.schema.json": ReviewDirectory.model_json_schema(),
        "organization-review-query.schema.json": ReviewQuery.model_json_schema(),
        "fleet-refresh-request.schema.json": FleetRefreshRequest.model_json_schema(),
        "fleet-refresh-receipt.schema.json": FleetRefreshReceipt.model_json_schema(),
        "fleet-refresh-status-request.schema.json": FleetRefreshStatusRequest.model_json_schema(),
        "fleet-refresh-status.schema.json": FleetRefreshStatus.model_json_schema(),
        "tenancy-directory.schema.json": TenancyDirectory.model_json_schema(),
        "tenancy-detail.schema.json": TenancyDetail.model_json_schema(),
        "required-users-directory.schema.json": RequiredUsersDirectory.model_json_schema(),
        "signing-key-view.schema.json": SigningKeyView.model_json_schema(),
        "signing-key-request.schema.json": SigningKeyRequest.model_json_schema(),
        "presence-check-request.schema.json": PresenceCheckRequest.model_json_schema(),
        "tenancy-query.schema.json": TenancyQuery.model_json_schema(),
        "organization-directory.schema.json": OrganizationDirectory.model_json_schema(),
        "organization-query.schema.json": OrganizationQuery.model_json_schema(),
        "organization-outcome.schema.json": OrganizationOutcome.model_json_schema(),
        "organization-evidence.schema.json": OrganizationEvidence.model_json_schema(),
        "branding-view.schema.json": BrandingView.model_json_schema(),
        "audit-directory.schema.json": AuditDirectory.model_json_schema(),
        "audit-query.schema.json": AuditQuery.model_json_schema(),
        "audit-export-query.schema.json": AuditExportQuery.model_json_schema(),
        "sandbox-config.schema.json": SandboxConfig.model_json_schema(),
        "inspection-submission.schema.json": InspectionSubmission.model_json_schema(),
        "sandbox-catalog.schema.json": SandboxCatalog.model_json_schema(),
        "operation-directory.schema.json": OperationDirectory.model_json_schema(),
        "operation-detail.schema.json": OperationDetail.model_json_schema(),
        "operation-query.schema.json": OperationQuery.model_json_schema(),
        "inspection-command.schema.json": InspectTenancy.model_json_schema(),
        "inspection-admission.schema.json": InspectImportRequest.model_json_schema(),
        "inspection-intent-event.schema.json": IntentEventData.model_json_schema(),
        "operation-acceptance.schema.json": Acceptance.model_json_schema(),
        "inspection-dispatch.schema.json": DispatchEvent.model_json_schema(),
        "inspection-outcome.schema.json": InspectionOutcome.model_json_schema(),
        "administrator-change.schema.json": AdministratorChange.model_json_schema(),
        "administrator-revoked.schema.json": AdministratorRevoked.model_json_schema(),
        "local-sign-in.schema.json": LocalSignIn.model_json_schema(),
        "security-evidence.schema.json": SecurityEvidence.model_json_schema(),
        "administrator-directory.schema.json": AdministratorDirectory.model_json_schema(),
        "administrator-query.schema.json": AdministratorQuery.model_json_schema(),
        "session-view.schema.json": SessionView.model_json_schema(),
        "application-settings.schema.json": ApplicationSettings.model_json_schema(),
        "inspection-result.schema.json": RESULT_ADAPTER.json_schema(),
    }


# Fail when checked artifacts differ; write only when explicitly invoked without --check.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    directory = ROOT / "backend/contracts"
    stale = []
    for name, schema in contracts().items():
        path = directory / name
        content = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.is_file() or path.read_text() != content:
                stale.append(name)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    print(
        json.dumps(
            {
                "mode": "check" if args.check else "write",
                "schemas": len(contracts()),
                "stale": stale,
            }
        )
    )
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
