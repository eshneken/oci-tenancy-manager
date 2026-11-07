// Generated from authoritative Pydantic schemas.
export type CheckAvailable = boolean;
export type CheckUnavailableReason =
  | (
      | "not_configured"
      | "tenancy_inactive"
      | "tenancy_busy"
      | "provider_unavailable"
    )
  | null;
export type PendingOperationId = string | null;
export type ProviderMode = "simulated";
export type TenancyId = string;
export type TenancyStatus =
  "pending" | "active" | "terminating" | "terminated" | "failed" | "cancelled";
/**
 * @minItems 2
 * @maxItems 2
 */
export type Users = [RequiredUserRecord, RequiredUserRecord];
export type DomainOcid = string;
export type RecordedAt = string;
export type RetiredAt = string | null;
export type ScimResourceId = string;
export type SourceOperationId = string;
export type UserName = string;
export type UserOcid = string;
export type IdentityState = "recorded" | "not_recorded" | "retired";
export type CheckedAt = string | null;
export type OperationId = string | null;
export type Stale = boolean;
export type State = "not_checked" | "present" | "missing" | "unknown";
export type Purpose = "automation" | "recovery";
export type ClientRequestKey = string;
export type ClientRequestKey1 = string;
export type TenancyId1 = string | null;
export type AcceptedAt = string;
export type AcceptedCount = number;
export type JoinedCount = number;
export type OperationIds = string[];
export type ProviderMode1 = "simulated";
export type SkippedCount = number;
export type Actual = string | null;
export type ActualOverBudget = boolean;
export type Budget = string | null;
export type CanRefresh = boolean;
export type ComputedAt = string | null;
export type Currency = "USD" | null;
export type BudgetProcessingPeriodStartOffset = number | null;
export type EndDate = string | null;
export type ProcessingPeriodType = string;
export type ResetPeriod = string;
export type StartDate = string | null;
export type DesiredBudget = string | null;
export type Forecast = string | null;
export type ForecastOverBudget = boolean;
export type LatestFailure =
  | (
      | "COST_READ_COMPLETE"
      | "COST_READ_UNAVAILABLE"
      | "COST_SOURCE_UNQUALIFIED"
      | "COST_TARGET_CHANGED"
      | "COST_AUTHORIZATION_CHANGED"
      | "COST_CONTEXT_UNAVAILABLE"
      | "COST_READ_SUPERSEDED"
      | "COST_RETRIES_EXHAUSTED"
    )
  | null;
export type MinorUnits = 2 | null;
export type OperationId1 = string | null;
export type Pending = boolean;
export type PeriodEnd = string | null;
export type PeriodStart = string | null;
export type RetrievedAt = string | null;
export type State1 =
  | "not_collected"
  | "current"
  | "partial"
  | "stale"
  | "prior_cycle"
  | "unavailable"
  | "unqualified";
export type EffectiveTestEmail = string | null;
export type Environment = "local" | "staging" | "production";
export type Redirected = boolean;
export type EffectiveEmail = string | null;
export type Environment1 = "local" | "staging" | "production";
export type OriginalEmail = string | null;
export type PolicyHash = string;
export type Redirected1 = boolean;
export type EffectiveEmail1 = string | null;
export type Environment2 = "local" | "staging" | "production";
export type OriginalEmail1 = string | null;
export type PolicyHash1 = string;
export type Redirected2 = boolean;
export type Attempts = number;
export type CreatedAt = string;
export type Event = "action_required" | "terminal_failure" | "cost_read_failed";
export type Id = string;
export type LastAttemptAt = string | null;
export type OriginalRecipient = string | null;
export type Recipient = string | null;
export type Redirected3 = boolean;
export type SafeCode = string | null;
export type State2 =
  | "pending"
  | "blocked"
  | "sending"
  | "sent"
  | "failed"
  | "unknown"
  | "superseded";
export type UpdatedAt = string;
export type ClientRequestKey2 = string;
export type ExpectedRevision = number;
/**
 * @minItems 1
 * @maxItems 4
 */
export type Categories =
  | ["policy" | "quota" | "budget" | "tags"]
  | [
      "policy" | "quota" | "budget" | "tags",
      "policy" | "quota" | "budget" | "tags"
    ]
  | [
      "policy" | "quota" | "budget" | "tags",
      "policy" | "quota" | "budget" | "tags",
      "policy" | "quota" | "budget" | "tags"
    ]
  | [
      "policy" | "quota" | "budget" | "tags",
      "policy" | "quota" | "budget" | "tags",
      "policy" | "quota" | "budget" | "tags",
      "policy" | "quota" | "budget" | "tags"
    ];
export type TenancyId2 = string;
export type CheckingCount = number;
export type ConfirmedCount = number;
export type BaselineId = string | null;
export type BaselineVersionNumber = number | null;
export type CanCheck = boolean;
export type BindingOcid = string | null;
export type Category = "policy" | "quota" | "budget" | "tags";
export type EvidenceAt = string | null;
export type Expected = string | null;
export type Observed = string | null;
export type Retained = boolean;
export type SafeCode1 =
  | (
      | "MATCHING"
      | "MISSING"
      | "DIFFERENT"
      | "READ_UNAVAILABLE"
      | "BINDING_CONFLICT"
      | "UNBOUND_CONFIGURATION"
      | "ASSIGNMENT_CHANGED"
      | "AUTHORIZATION_CHANGED"
      | "TENANCY_BUSY"
      | "PROVIDER_UNAVAILABLE"
      | "CHECK_STALE"
    )
  | null;
export type State3 =
  | ("matching" | "missing" | "different" | "unavailable" | "conflict")
  | "not_checked";
export type Categories1 = ConfigurationIssue[];
export type CheckedAt1 = string | null;
export type ConfirmedIssueCount = number;
export type IssueCount = number;
export type LastOperationId = string | null;
export type OverrideCategories = ("policy" | "quota" | "budget" | "tags")[];
export type PendingOperationId1 = string | null;
export type Stale1 = boolean;
export type State4 =
  | ("matching" | "drifted" | "unavailable" | "superseded")
  | ("not_checked" | "checking");
export type TenancyId3 = string;
export type TenancyName = string;
export type Items = ConfigurationCheckSummary[];
export type Page = number;
export type PageSize = number;
export type Pages = number;
export type ProviderMode2 = "simulated";
export type StaleCount = number;
export type Total = number;
export type UnavailableCount = number;
export type UncheckedCount = number;
export type Direction = "asc" | "desc";
export type Page1 = number;
export type PageSize1 = 10 | 25 | 50;
export type Query = string;
export type Sort = "name" | "checked_at" | "issue_count";
export type State5 =
  | "all"
  | "matching"
  | "drifted"
  | "unavailable"
  | "not_checked"
  | "checking"
  | "stale";
export type Tab = "confirmed" | "checks";
export type TenancyId4 = string | null;
export type BaselineId1 = string | null;
export type BaselineVersionNumber1 = number | null;
export type CanCheck1 = boolean;
export type Categories2 = ConfigurationIssue[];
export type CheckedAt2 = string | null;
export type ConfirmedIssueCount1 = number;
export type IssueCount1 = number;
export type LastOperationId1 = string | null;
export type OverrideCategories1 = ("policy" | "quota" | "budget" | "tags")[];
export type PendingOperationId2 = string | null;
export type Stale2 = boolean;
export type State6 =
  | ("matching" | "drifted" | "unavailable" | "superseded")
  | ("not_checked" | "checking");
export type TenancyId5 = string;
export type TenancyName1 = string;
export type ClientRequestKey3 = string;
export type TenancyId6 = string | null;
export type BasedOnId = string | null;
export type BudgetCurrency = string;
export type BudgetPeriod = "MONTHLY";
export type MonthlyBudgetAmount = number | string;
/**
 * @minItems 1
 * @maxItems 50
 */
export type PolicyStatements = [string, ...string[]];
/**
 * @minItems 1
 * @maxItems 50
 */
export type QuotaStatements = [string, ...string[]];
export type Key = string;
export type Value = string;
/**
 * @maxItems 100
 */
export type TagDefaults = TagDefault[];
export type TagNamespace = "OTM";
export type ContentHash = string;
export type CreatedAt1 = string;
export type CreatedBy = string;
export type EditRevision = number;
export type Id1 = string;
export type PublicationMode = "simulated" | null;
export type PublishedAt = string | null;
export type PublishedBy = string | null;
export type PublishedByName = string | null;
export type VersionNumber = number;
export type CanEdit = boolean;
export type BaselineVersionId = string;
export type CreatedAt2 = string;
export type CreatedBy1 = string;
export type EffectiveHash = string;
export type Id2 = string;
export type MonthlyBudgetOverrideAmount = number | string | null;
export type OperationId2 = string;
export type PolicyOverrideStatements = [string, ...string[]] | null;
export type PreviousId = string | null;
export type QuotaOverrideStatements = [string, ...string[]] | null;
export type ResolutionContractVersion = "simulated-config-1";
export type RevisionNumber = number;
export type TenancyId7 = string;
export type TenancyId8 = string;
export type TenancyName2 = string;
export type TenancyRevision = number;
export type MonthlyBudgetOverrideAmount1 = number | string | null;
export type PolicyOverrideStatements1 = [string, ...string[]] | null;
export type QuotaOverrideStatements1 = [string, ...string[]] | null;
export type BaselineVersionId1 = string;
export type ConfigurationId = string | null;
export type TenancyRevision1 = number;
export type TenancyId9 = string;
export type Id3 = string;
export type OperationId3 = string | null;
export type Code =
  | "TENANCY_BUSY"
  | "REGISTERED_CHILD_REQUIRED"
  | "PROVIDER_UNAVAILABLE"
  | "OVERRIDE_REVIEW_REQUIRED"
  | "OVERRIDE_CONTEXT_UNAVAILABLE";
export type Name = string;
export type OperationId4 = string | null;
export type TenancyId10 = string;
export type Blockers = ConfigurationBlocker[];
export type PolicyChoice = ("use_new_baseline" | "keep_override") | null;
export type PolicyReview = boolean;
export type QuotaChoice = ("use_new_baseline" | "keep_override") | null;
export type QuotaReview = boolean;
export type TenancyId11 = string;
export type TenancyName3 = string;
export type Conflicts = OverrideConflict[];
export type PendingCount = number;
export type PreviewHash = string;
export type ReadyCount = number;
export type TenancyId12 = string | null;
export type Revision = number;
export type State7 = "draft" | "accepted" | "stale";
export type ClientRequestKey4 = string;
export type TenancyId13 = string | null;
export type ExpectedRevision1 = number;
export type PolicyChoice1 = ("use_new_baseline" | "keep_override") | null;
export type QuotaChoice1 = ("use_new_baseline" | "keep_override") | null;
export type TenancyId14 = string;
export type Blockers1 = ConfigurationBlocker[];
export type Conflicts1 = OverrideConflict[];
export type PendingCount1 = number;
export type PreviewHash1 = string;
export type ReadyCount1 = number;
export type TenancyId15 = string | null;
export type ClientRequestKey5 = string;
export type OverrideMode = boolean;
export type PlanId = string | null;
export type PreviewHash2 = string;
export type RepairCategories = ("policy" | "quota" | "budget" | "tags")[];
export type TenancyId16 = string | null;
export type CanRetry = boolean;
export type ChangeKind = "baseline_update" | "override_change" | "repair";
export type OperationId5 = string;
export type State8 = string;
export type Name1 = string;
export type SafeCode2 = string | null;
export type State9 = "pending" | "verified" | "needs_attention";
export type TenancyId17 = string;
export type VerifiedAt = string | null;
export type Targets = ConfigurationTargetProgress[];
export type Configured = boolean;
/**
 * @maxItems 50
 */
export type Items1 = BaselineVersion[];
export type Page2 = number;
export type PageSize2 = number;
export type Pages1 = number;
export type PublicationAvailable = boolean;
export type Total1 = number;
export type ContentHash1 = string;
export type CreatedAt3 = string;
export type CreatedBy2 = string;
export type EditRevision1 = number;
export type Id4 = string;
export type VersionNumber1 = number;
export type BasedOnId1 = string | null;
export type BaselineId2 = string | null;
export type ExpectedRevision2 = number | null;
export type BasedOnId2 = string | null;
export type ContentHash2 = string;
export type CreatedAt4 = string;
export type CreatedBy3 = string;
export type EditRevision2 = number;
export type Id5 = string;
export type PublicationMode1 = "simulated" | null;
export type PublishedAt1 = string | null;
export type PublishedBy1 = string | null;
export type PublishedByName1 = string | null;
export type VersionNumber2 = number;
export type BaselineId3 = string | null;
export type Page3 = number;
export type PageSize3 = 10 | 25 | 50;
export type BaselineId4 = string;
export type ExpectedRevision3 = number;
export type Available = boolean;
export type Blockers2 = string[];
export type RootEmail = string;
export type RootName = string | null;
/**
 * @minItems 1
 * @maxItems 50
 */
export type Segments = [MappingSegment, ...MappingSegment[]];
/**
 * @maxItems 50
 */
export type DesigneeEmails = string[];
export type Id6 = string | null;
export type Label = string;
export type LeaderEmail = string;
export type Configured1 = boolean;
export type AppliedVersionId = string | null;
export type ConfigurationId1 = string | null;
export type ProposedVersionId = string | null;
export type RegistryRevision = number;
export type HasFeed = boolean;
export type Email = string;
export type Role = "leader" | "designee";
export type SegmentId = string;
export type SegmentName = string;
export type Status =
  | "healthy"
  | "departed"
  | "excluded"
  | "profile_missing"
  | "ancestry_incomplete"
  | "branch_changed"
  | "not_verified";
export type Roles = MappingRole[];
export type RootEditable = boolean;
export type ChangeRoot = boolean;
export type ChangeRoot1 = boolean;
export type PreviewToken = string;
export type AffectedCount = number;
export type Blockers3 = string[];
export type SegmentId1 = string;
export type Changes = MappingChange[];
export type HasFeed1 = boolean;
export type AfterAncestry = "root" | "resolved" | "incomplete";
export type AfterDesignees = string[];
export type AfterLeader = string | null;
export type AfterSegment = string | null;
export type BeforeAncestry = "root" | "resolved" | "incomplete";
export type BeforeDesignees = string[];
export type BeforeLeader = string | null;
export type BeforeSegment = string | null;
export type Email1 = string;
export type Name2 = string;
export type PersonId = string;
export type Items2 = MappingImpact[];
export type Page4 = number;
export type Pages2 = number;
export type PreviewToken1 = string;
export type Roles1 = MappingRole[];
export type RootBefore = string | null;
export type RootNameBefore = string | null;
export type RootPresent = boolean;
export type UnassignedCount = number;
export type UnresolvedCount = number;
export type ClientRequestKey6 = string;
export type ConfirmDeletion = boolean;
export type ConfirmManager = boolean;
export type ConfirmShared = boolean;
export type AppliedVersionId1 = string;
export type ConfigurationId2 = string;
export type ProposedVersionId1 = string;
export type RegistryRevision1 = number;
export type Kind = "delete_registered_tenancy";
export type TenancyId18 = string;
export type ManagerWarning = boolean;
export type Email2 = string;
export type IsManager = boolean;
export type LeavesDirectory = boolean;
export type Name3 = string;
export type OtherTenancyCount = number;
export type PersonId1 = string;
export type Role1 = "owner" | "member";
export type People1 = DeletionPerson[];
export type SharedWarning = boolean;
export type BaselineVersionId2 = string | null;
export type BaselineVersionNumber2 = number | null;
export type CleanupCount = number;
export type ConfigurationCheckStale = boolean;
export type ConfigurationCheckState =
  | "matching"
  | "drifted"
  | "unavailable"
  | "superseded"
  | "not_checked"
  | "checking";
export type ConfigurationCheckedAt = string | null;
export type ConfigurationConfirmedIssueCount = number;
export type ConfigurationIssueCount = number;
export type ConfigurationVerifiedAt = string | null;
export type Actual1 = string | null;
export type ActualOverBudget1 = boolean;
export type Budget1 = string | null;
export type CanRefresh1 = boolean;
export type ComputedAt1 = string | null;
export type Currency1 = "USD" | null;
export type DesiredBudget1 = string | null;
export type Forecast1 = string | null;
export type ForecastOverBudget1 = boolean;
export type LatestFailure1 =
  | (
      | "COST_READ_COMPLETE"
      | "COST_READ_UNAVAILABLE"
      | "COST_SOURCE_UNQUALIFIED"
      | "COST_TARGET_CHANGED"
      | "COST_AUTHORIZATION_CHANGED"
      | "COST_CONTEXT_UNAVAILABLE"
      | "COST_READ_SUPERSEDED"
      | "COST_RETRIES_EXHAUSTED"
    )
  | null;
export type MinorUnits1 = 2 | null;
export type OperationId6 = string | null;
export type Pending1 = boolean;
export type PeriodEnd1 = string | null;
export type PeriodStart1 = string | null;
export type RetrievedAt1 = string | null;
export type State10 =
  | "not_collected"
  | "current"
  | "partial"
  | "stale"
  | "prior_cycle"
  | "unavailable"
  | "unqualified";
export type CreatedAt5 = string;
export type DesiredConfigurationId = string | null;
export type HasPendingOperation = boolean;
export type HomeRegion = string;
export type Id7 = string;
export type Kind1 = "individual" | "shared";
export type LastVerifiedConfigurationId = string | null;
export type LeaderName = string | null;
export type LobName = string | null;
export type ManagerName = string | null;
export type MemberCount = number;
export type Name4 = string;
export type OperationCompletedAt = string | null;
export type OperationId7 = string | null;
export type OperationState = string | null;
export type Origin = "create" | "import";
export type OverrideCategories2 = ("policy" | "quota" | "budget")[];
export type OwnerEmail = string | null;
export type OwnerName = string | null;
export type OwnerPersonId = string | null;
export type ParentTenancyOcid = string;
export type ProviderMode3 = "simulated";
export type Checking = boolean;
export type State11 =
  "not_checked" | "present" | "missing" | "unavailable" | "stale";
export type Status1 = string;
export type TenancyOcid = string;
export type VerifiedAt1 = string | null;
export type VerifiedBaselineVersionId = string | null;
export type VerifiedBaselineVersionNumber = number | null;
export type Action = "verify_handoff" | "start_setup";
export type ClientRequestKey7 = string;
export type ConfirmCleanup = boolean;
export type ActivationUserOcid = string | null;
export type BootstrapUserOcid = string;
export type TenancyOcid1 = string;
export type Revision1 = number;
export type AdministratorEmail = string | null;
export type AdministratorName = string;
export type AvailableActions = ("verify_handoff" | "start_setup")[];
export type BootstrapUsername = string;
export type CanAct = boolean;
export type Key1 = string;
export type Label1 = string;
export type State12 = "pending" | "verified" | "needs_attention";
export type VerifiedAt2 = string | null;
export type Checks = OnboardingCheck[];
export type ActivationScimId = string | null;
export type ActivationUserOcid1 = string | null;
export type BootstrapScimId = string;
export type BootstrapUserOcid1 = string;
export type DomainOcid1 = string;
export type HomeRegion1 = string;
export type Name5 = string;
export type OrganizationId = string;
export type ParentTenancyOcid1 = string;
export type TenancyOcid2 = string;
export type ExpectedParentTenancyOcid = string;
export type IssueCode = string | null;
export type OperationId8 = string;
export type Origin1 = "create" | "import";
export type OwnerName1 = string;
export type Phase =
  | "preparing"
  | "handoff"
  | "review"
  | "configuring"
  | "complete"
  | "blocked"
  | "cancelled";
export type PublicKey = string | null;
export type RequestedHomeRegion = string | null;
export type RequestedName = string | null;
export type Revision2 = number;
export type State13 = string;
export type TenancyId19 = string;
export type Action1 =
  | "create_tenancy"
  | "import_tenancy"
  | "join_shared"
  | "offboard_person"
  | "delete_tenancy"
  | "remove_member"
  | "transfer_owner"
  | "no_tenancy_required"
  | "keep_without_tenancy"
  | "ignore"
  | "resolve"
  | "merge"
  | "reonboard"
  | "mark_returned"
  | "cancel_simulation";
export type ClientRequestKey8 = string;
export type CompartmentName = string | null;
export type ConfirmDestructive = boolean;
export type ConfirmManager1 = boolean;
export type ConfirmNoAssociations = boolean;
export type ConfirmShared1 = boolean;
export type ExistingCompartmentOcid = string | null;
export type FormerOwnerDisposition = ("keep_member" | "remove") | null;
export type HomeRegion2 = string | null;
export type ImportOcid = string | null;
export type Name6 = string | null;
export type OperationId9 = string | null;
export type ParentCompartmentOcid = string | null;
export type PartnerPersonId = string | null;
export type PersonId2 = string;
export type Action2 = "delete" | "transfer" | "remove" | "keep";
export type AssociationId = string;
export type FormerOwnerDisposition1 = ("keep_member" | "remove") | null;
export type RecipientPersonId = string | null;
/**
 * @maxItems 100
 */
export type Plan = AssociationChoice[];
export type RecipientPersonId1 = string | null;
export type ReviewId = string | null;
export type TenancyId20 = string | null;
export type TenancyKind = "individual" | "shared";
export type AcceptedAt1 = string;
export type OperationId10 = string | null;
export type ProviderMode4 = "simulated" | "application";
export type State14 =
  | "queued"
  | "succeeded"
  | "running"
  | "needs_attention"
  | "failed"
  | "cancelled"
  | "waiting";
export type Actions = (
  | "create_tenancy"
  | "import_tenancy"
  | "join_shared"
  | "offboard_person"
  | "delete_tenancy"
  | "remove_member"
  | "transfer_owner"
  | "no_tenancy_required"
  | "keep_without_tenancy"
  | "ignore"
  | "resolve"
  | "merge"
  | "reonboard"
  | "mark_returned"
  | "cancel_simulation"
)[];
export type Actions1 = ("delete" | "transfer" | "remove" | "keep")[];
export type CleanupRequired = boolean;
export type CompartmentName1 = string | null;
export type CompartmentOcid = string | null;
export type Id8 = string;
export type OperationId11 = string | null;
export type PersonId3 = string;
export type Role2 = "owner" | "member";
export type Status2 = string;
export type TenancyId21 = string;
export type TenancyKind1 = "individual" | "shared";
export type TenancyName4 = string;
export type TenancyStatus1 = string;
export type UserOcid1 = string | null;
export type Associations = AssociationView[];
export type Identifier = string;
export type Name7 = string;
export type CreationRegions = CreationRegion[];
export type DirectoryStatus = string;
export type IsManager1 = boolean;
export type MappingRequired = boolean;
export type Email3 = string;
export type Id9 = string;
export type Name8 = string;
export type MergePartners = PersonOption[];
export type PendingOperationId3 = string | null;
export type ProviderMode5 = "simulated" | "unavailable";
export type Category1 = "actionable" | "informational" | "change";
export type Email4 = string;
export type FirstSeenAt = string;
export type Id10 = string;
export type Kind2 = string;
export type LastSeenAt = string;
export type Name9 = string;
export type OperationId12 = string | null;
export type PersonId4 = string | null;
export type Resolution = string | null;
export type ResolvedAt = string | null;
export type Status3 = "open" | "resolved" | "ignored";
export type SharedTenancies = TenancyView[];
export type SourcePresent = boolean;
export type TransferRecipients = PersonOption[];
export type ActionableCount = number;
export type HistoryCount = number;
export type InformationalCount = number;
export type Items3 = ReviewView[];
export type Page5 = number;
export type PageSize4 = number;
export type Pages3 = number;
export type Total2 = number;
export type Category2 = "actionable" | "informational" | "history";
export type Direction1 = "asc" | "desc";
export type Page6 = number;
export type PageSize5 = 10 | 25 | 50;
export type Query1 = string;
export type Sort1 = "first_seen_at" | "name" | "kind" | "status";
export type CanRefreshCosts = boolean;
export type CostsPendingCount = number;
export type IndividualCount = number;
export type IssueCount2 = number;
export type Items4 = TenancyView[];
export type LatestBaselineId = string | null;
export type LatestBaselineVersionNumber = number | null;
export type Page7 = number;
export type PageSize6 = number;
export type Pages4 = number;
export type PendingCount2 = number;
export type SharedCount = number;
export type Total3 = number;
export type TotalTenancies = number;
export type Name10 = string;
export type Ocid = string;
export type CompartmentParents = CompartmentOption[];
export type ConfigurationOperationId = string | null;
export type Memberships = AssociationView[];
export type OnboardingOperationId = string | null;
export type People3 = PersonOption[];
export type Direction2 = "asc" | "desc";
export type Page8 = number;
export type PageSize7 = 10 | 25 | 50;
export type Query2 = string;
export type SharedOnly = boolean;
export type Sort2 =
  | "name"
  | "owner_name"
  | "manager_name"
  | "lob_name"
  | "member_count"
  | "actual"
  | "budget"
  | "forecast";
export type AbsenceCount = number;
export type AbsenceEligible = boolean;
export type ActionableCount1 = number;
export type AppliedAt = string | null;
export type Configured2 = boolean;
export type EmployeeCount = number;
export type At = string;
export type Category3 = "actionable" | "informational" | "change";
export type Code1 = string;
export type Detail = string;
export type Email5 = string;
export type EmployeeName = string;
export type Findings = OrganizationFinding[];
export type HistoryCount1 = number;
export type AbsenceReview = boolean;
export type DirectoryStatus1 =
  "included" | "exempt" | "offboarded" | "outside" | "merged";
export type Email6 = string;
export type FullName = string;
export type Id11 = string;
export type LeaderName1 = string | null;
export type LobName1 = string | null;
export type ManagerName1 = string | null;
export type PendingOperationId4 = string | null;
export type PendingTenancyCount = number;
export type TenancyCount = number;
export type Items5 = EmployeeView[];
export type AffectedEmail = string | null;
export type Code2 = string;
export type Fatal = boolean;
export type Diagnostics = Diagnostic[];
export type OriginalState = string | null;
export type ProposedVersionId2 = string | null;
export type RevisionId = string | null;
export type SnapshotId = string;
export type State15 =
  "received" | "staged" | "published" | "rejected" | "superseded" | "duplicate";
export type Page9 = number;
export type PageSize8 = number;
export type Pages5 = number;
export type PendingWorkflows = number;
export type ProviderMode6 = "simulated" | "unavailable";
export type ServerTime = string;
export type SourceAsOf = string | null;
export type TestResetEnabled = boolean;
export type Total4 = number;
export type UploadEnabled = boolean;
export type WorkflowsEnabled = boolean;
export type Direction3 = "asc" | "desc";
export type IncludeRemoved = boolean;
export type Page10 = number;
export type PageSize9 = 10 | 25 | 50;
export type Query3 = string;
export type Sort3 =
  | "full_name"
  | "email"
  | "manager_name"
  | "leader_name"
  | "lob_name"
  | "tenancy_count";
export type Diagnostics1 = Diagnostic[];
export type OriginalState1 = string | null;
export type ProposedVersionId3 = string | null;
export type RevisionId1 = string | null;
export type SnapshotId1 = string;
export type State16 =
  "received" | "staged" | "published" | "rejected" | "superseded" | "duplicate";
export type DisplayName = string;
export type IconUrl = string | null;
export type LogoUrl = string | null;
export type AuthorizationRevision = string;
export type DisplayName1 = string;
export type Email7 = string | null;
export type Id12 = string;
export type IdentityKind = "local_recovery" | "corporate_sso";
export type Status4 = "active" | "revoked";
export type Items6 = AdministratorView[];
export type Page11 = number;
export type PageSize10 = number;
export type Pages6 = number;
export type Active = number;
export type ProtectedRecovery = number;
export type Total5 = number;
export type Total6 = number;
export type Direction4 = "asc" | "desc";
export type Page12 = number;
export type PageSize11 = 10 | 25 | 50 | 100;
export type Query4 = string;
export type Sort4 = "display_name" | "email" | "identity_kind" | "status";
export type DisplayName2 = string | null;
export type ExpiresAt = string;
export type WorkspaceId = string;
export type AttentionCount = number;
export type AcceptedAt2 = string;
export type CanTakeResponsibility = boolean;
export type CompletedAt = string | null;
export type GuidedOnboarding = boolean;
export type Id13 = string;
export type InitiatedBy = string | null;
export type Kind3 =
  | "inspect_import"
  | "organization_action"
  | "configuration_update"
  | "configuration_check"
  | "cost_collection"
  | "required_user_check";
export type ProviderMode7 = "simulated";
export type ResponsibilityRevision = number | null;
export type ResponsibleAdministratorId = string | null;
export type ResponsibleAdministratorName = string | null;
export type ResultTenancyId = string | null;
export type Stage = string;
export type State17 =
  | "queued"
  | "running"
  | "waiting"
  | "needs_attention"
  | "succeeded"
  | "cancelled"
  | "failed";
export type TargetLabel = string | null;
export type TargetTenancyOcid = string | null;
export type Title = string | null;
export type UpdatedAt1 = string;
export type Items7 = OperationSummary[];
export type Page13 = number;
export type PageSize12 = number;
export type Pages7 = number;
export type Total7 = number;
export type At1 = string;
export type Kind4 =
  | "operation_responsibility_changed"
  | "email_delivery"
  | "operation_intent"
  | "inspection_dispatch"
  | "inspection_outcome"
  | "organization_action_outcome"
  | "onboarding_action"
  | "onboarding_outcome"
  | "configuration_outcome"
  | "configuration_retry"
  | "configuration_check_outcome"
  | "cost_collection_outcome"
  | "required_user_check_outcome";
export type SafeCode3 = string | null;
export type Events = OperationEventView[];
export type EventsLimited = boolean;
export type Attempts1 = number;
export type CreatedAt6 = string;
export type Event1 =
  "action_required" | "terminal_failure" | "cost_read_failed";
export type Id14 = string;
export type LastAttemptAt1 = string | null;
export type OriginalRecipient1 = string | null;
export type Recipient1 = string | null;
export type Redirected4 = boolean;
export type SafeCode4 = string | null;
export type State18 =
  | "pending"
  | "blocked"
  | "sending"
  | "sent"
  | "failed"
  | "unknown"
  | "superseded";
export type UpdatedAt2 = string;
export type Notifications = NotificationSummary1[];
export type AttemptNumber = number;
export type SafeCode5 = string | null;
export type State19 = "running" | "verified" | "needs_attention";
export type StepKey = string;
export type VerifiedAt3 = string | null;
export type Steps = OperationStepView[];
export type Direction5 = "asc" | "desc";
export type Page14 = number;
export type PageSize13 = 10 | 25 | 50 | 100;
export type Query5 = string;
export type Sort5 = "accepted_at" | "updated_at" | "state" | "stage";
export type State20 =
  | ""
  | "queued"
  | "running"
  | "waiting"
  | "needs_attention"
  | "succeeded"
  | "cancelled"
  | "failed";
export type AcceptedAt3 = string;
export type OperationId13 = string;
export type State21 =
  | "queued"
  | "running"
  | "waiting"
  | "needs_attention"
  | "succeeded"
  | "cancelled"
  | "failed";
export type ClientRequestKey9 = string;
export type TenancyOcid3 = string;
export type ExecutionPaused = boolean;
export type ProviderMode8 = "simulated";
export type Name11 = string;
export type Scenario =
  "healthy" | "access_denied" | "timeout" | "unsupported" | "unobservable";
export type TenancyOcid4 = string;
export type Targets1 = SandboxTarget[];
export type ActorName = string | null;
export type AdministratorId = string | null;
export type AdministratorName1 = string | null;
export type At2 = string;
export type BaselineId5 = string | null;
export type Category4 =
  | "authentication"
  | "administration"
  | "operations"
  | "organization"
  | "email_delivery";
/**
 * @maxItems 512
 */
export type Changes1 = string[];
export type Id15 = string;
export type Kind5 =
  | "email_delivery"
  | "operation_responsibility_changed"
  | "configuration_check_outcome"
  | "cost_collection_outcome"
  | "required_user_check_outcome"
  | "cost_refresh_requested"
  | "configuration_review_staged"
  | "baseline_draft_saved"
  | "baseline_published"
  | "baseline_default_changed"
  | "operation_intent"
  | "inspection_dispatch"
  | "inspection_outcome"
  | "organization_action_outcome"
  | "onboarding_action"
  | "onboarding_outcome"
  | "configuration_outcome"
  | "configuration_retry"
  | "administrator_revoked"
  | "administrator_bootstrapped"
  | "local_credentials_reset"
  | "local_sign_in_succeeded"
  | "local_sign_in_failed"
  | "session_logged_out"
  | "audit_export"
  | "organization_configured"
  | "organization_feed_received"
  | "organization_feed_rejected"
  | "organization_published"
  | "organization_review_decided";
export type OperationId14 = string | null;
export type OrganizationSubjectName = string | null;
export type Id16 = string;
export type Kind6 = "tenancy" | "person";
export type Name12 = string;
/**
 * @maxItems 501
 */
export type Resources = AuditResource[];
export type SafeCode6 = string | null;
export type Summary = string | null;
export type Items8 = AuditEntry[];
export type Page15 = number;
export type PageSize14 = number;
export type Pages8 = number;
export type Total8 = number;
export type Category5 =
  | ""
  | "authentication"
  | "administration"
  | "operations"
  | "organization"
  | "email_delivery";
export type Direction6 = "asc" | "desc";
export type FromAt = string | null;
export type Page16 = number;
export type PageSize15 = 10 | 25 | 50 | 100;
export type Query6 = string;
export type Sort6 = "at" | "kind" | "actor_name";
export type ToAt = string | null;
export type Category6 =
  | ""
  | "authentication"
  | "administration"
  | "operations"
  | "organization"
  | "email_delivery";
export type Direction7 = "asc" | "desc";
export type FromAt1 = string | null;
export type Query7 = string;
export type Sort7 = "at" | "kind" | "actor_name";
export type ToAt1 = string | null;

export interface ApiContracts {
  RequiredUsersDirectory: RequiredUsersDirectory;
  PresenceCheckRequest: PresenceCheckRequest;
  CostRefreshRequest: CostRefreshRequest;
  CostRefreshReceipt: CostRefreshReceipt;
  CostView: CostView;
  EmailPolicyView: EmailPolicyView;
  EmailContacts: EmailContacts;
  EmailRoute: EmailRoute1;
  NotificationSummary: NotificationSummary;
  ResponsibilityCommand: ResponsibilityCommand;
  ConfigurationRepairRequest: ConfigurationRepairRequest;
  ConfigurationDriftDirectory: ConfigurationDriftDirectory;
  ConfigurationDriftQuery: ConfigurationDriftQuery;
  ConfigurationCheckSummary: ConfigurationCheckSummary1;
  ConfigurationCheckRequest: ConfigurationCheckRequest;
  OverrideEditor: OverrideEditor;
  OverridePreviewRequest: OverridePreviewRequest;
  ConfigurationPlanView: ConfigurationPlanView;
  CreateConfigurationPlan: CreateConfigurationPlan;
  SaveConfigurationReview: SaveConfigurationReview;
  ConfigurationPreview: ConfigurationPreview1;
  ConfigurationUpdate: ConfigurationUpdate;
  ConfigurationProgress: ConfigurationProgress;
  BaselineDirectory: BaselineDirectory;
  BaselineDraft: BaselineDraft;
  SaveBaselineDraft: SaveBaselineDraft;
  BaselineVersion: BaselineVersion1;
  BaselineQuery: BaselineQuery;
  PublishBaseline: PublishBaseline;
  MappingSettings: MappingSettings;
  MappingRequest: MappingRequest;
  MappingApply: MappingApply;
  MappingPreview: MappingPreview;
  TenancyDeletionCommand: TenancyDeletionCommand;
  TenancyDeletionPreview: TenancyDeletionPreview;
  OnboardingCommand: OnboardingCommand;
  OnboardingView: OnboardingView;
  OrganizationAction: OrganizationAction;
  ActionReceipt: ActionReceipt;
  PersonWorkflow: PersonWorkflow;
  ReviewDirectory: ReviewDirectory;
  ReviewQuery: ReviewQuery;
  TenancyDirectory: TenancyDirectory;
  TenancyDetail: TenancyDetail;
  TenancyQuery: TenancyQuery;
  OrganizationDirectory: OrganizationDirectory;
  OrganizationQuery: OrganizationQuery;
  OrganizationOutcome: OrganizationOutcome1;
  BrandingView: BrandingView;
  AdministratorDirectory: AdministratorDirectory;
  AdministratorQuery: AdministratorQuery;
  SessionView: SessionView;
  OperationDirectory: OperationDirectory;
  OperationDetail: OperationDetail;
  OperationQuery: OperationQuery;
  Acceptance: Acceptance;
  InspectionSubmission: InspectionSubmission;
  SandboxCatalog: SandboxCatalog;
  AuditDirectory: AuditDirectory;
  AuditQuery: AuditQuery;
  AuditExportQuery: AuditExportQuery;
}
export interface RequiredUsersDirectory {
  check_available?: CheckAvailable;
  check_unavailable_reason?: CheckUnavailableReason;
  pending_operation_id?: PendingOperationId;
  provider_mode: ProviderMode;
  tenancy_id: TenancyId;
  tenancy_status: TenancyStatus;
  users: Users;
}
export interface RequiredUserRecord {
  identity: RequiredUserIdentity | null;
  identity_state: IdentityState;
  presence?: UserPresenceView;
  purpose: Purpose;
}
export interface RequiredUserIdentity {
  domain_ocid: DomainOcid;
  recorded_at: RecordedAt;
  retired_at: RetiredAt;
  scim_resource_id: ScimResourceId;
  source_operation_id: SourceOperationId;
  user_name: UserName;
  user_ocid: UserOcid;
}
export interface UserPresenceView {
  checked_at?: CheckedAt;
  operation_id?: OperationId;
  stale?: Stale;
  state?: State;
}
export interface PresenceCheckRequest {
  client_request_key: ClientRequestKey;
}
export interface CostRefreshRequest {
  client_request_key: ClientRequestKey1;
  tenancy_id?: TenancyId1;
}
export interface CostRefreshReceipt {
  accepted_at: AcceptedAt;
  accepted_count: AcceptedCount;
  joined_count: JoinedCount;
  operation_ids: OperationIds;
  provider_mode?: ProviderMode1;
  skipped_count: SkippedCount;
}
export interface CostView {
  actual?: Actual;
  actual_over_budget?: ActualOverBudget;
  budget?: Budget;
  can_refresh?: CanRefresh;
  computed_at?: ComputedAt;
  currency?: Currency;
  cycle_facts?: BudgetCycleFacts | null;
  desired_budget?: DesiredBudget;
  forecast?: Forecast;
  forecast_over_budget?: ForecastOverBudget;
  latest_failure?: LatestFailure;
  minor_units?: MinorUnits;
  operation_id?: OperationId1;
  pending?: Pending;
  period_end?: PeriodEnd;
  period_start?: PeriodStart;
  retrieved_at?: RetrievedAt;
  state?: State1;
}
export interface BudgetCycleFacts {
  budget_processing_period_start_offset: BudgetProcessingPeriodStartOffset;
  end_date?: EndDate;
  processing_period_type: ProcessingPeriodType;
  reset_period: ResetPeriod;
  start_date?: StartDate;
}
export interface EmailPolicyView {
  effective_test_email: EffectiveTestEmail;
  environment: Environment;
  redirected: Redirected;
}
export interface EmailContacts {
  activation: EmailRoute;
  owner: EmailRoute;
  people?: People;
}
export interface EmailRoute {
  effective_email: EffectiveEmail;
  environment: Environment1;
  original_email: OriginalEmail;
  policy_hash: PolicyHash;
  redirected: Redirected1;
}
export interface People {
  [k: string]: EmailRoute;
}
export interface EmailRoute1 {
  effective_email: EffectiveEmail1;
  environment: Environment2;
  original_email: OriginalEmail1;
  policy_hash: PolicyHash1;
  redirected: Redirected2;
}
export interface NotificationSummary {
  attempts: Attempts;
  created_at: CreatedAt;
  event: Event;
  id: Id;
  last_attempt_at?: LastAttemptAt;
  original_recipient: OriginalRecipient;
  recipient: Recipient;
  redirected: Redirected3;
  safe_code?: SafeCode;
  state: State2;
  updated_at: UpdatedAt;
}
export interface ResponsibilityCommand {
  client_request_key: ClientRequestKey2;
  expected_revision: ExpectedRevision;
}
export interface ConfigurationRepairRequest {
  categories: Categories;
  tenancy_id: TenancyId2;
}
export interface ConfigurationDriftDirectory {
  checking_count: CheckingCount;
  confirmed_count: ConfirmedCount;
  items: Items;
  page: Page;
  page_size: PageSize;
  pages: Pages;
  provider_mode?: ProviderMode2;
  stale_count?: StaleCount;
  total: Total;
  unavailable_count: UnavailableCount;
  unchecked_count: UncheckedCount;
}
export interface ConfigurationCheckSummary {
  baseline_id: BaselineId;
  baseline_version_number: BaselineVersionNumber;
  can_check?: CanCheck;
  categories: Categories1;
  checked_at: CheckedAt1;
  confirmed_issue_count: ConfirmedIssueCount;
  issue_count: IssueCount;
  last_operation_id: LastOperationId;
  override_categories: OverrideCategories;
  pending_operation_id: PendingOperationId1;
  stale?: Stale1;
  state: State4;
  tenancy_id: TenancyId3;
  tenancy_name: TenancyName;
}
export interface ConfigurationIssue {
  binding_ocid: BindingOcid;
  category: Category;
  evidence_at: EvidenceAt;
  expected: Expected;
  observed: Observed;
  retained?: Retained;
  safe_code: SafeCode1;
  state: State3;
}
export interface ConfigurationDriftQuery {
  direction?: Direction;
  page?: Page1;
  page_size?: PageSize1;
  query?: Query;
  sort?: Sort;
  state?: State5;
  tab?: Tab;
  tenancy_id?: TenancyId4;
}
export interface ConfigurationCheckSummary1 {
  baseline_id: BaselineId1;
  baseline_version_number: BaselineVersionNumber1;
  can_check?: CanCheck1;
  categories: Categories2;
  checked_at: CheckedAt2;
  confirmed_issue_count: ConfirmedIssueCount1;
  issue_count: IssueCount1;
  last_operation_id: LastOperationId1;
  override_categories: OverrideCategories1;
  pending_operation_id: PendingOperationId2;
  stale?: Stale2;
  state: State6;
  tenancy_id: TenancyId5;
  tenancy_name: TenancyName1;
}
export interface ConfigurationCheckRequest {
  client_request_key: ClientRequestKey3;
  tenancy_id?: TenancyId6;
}
export interface OverrideEditor {
  baseline: BaselineVersion;
  can_edit: CanEdit;
  configuration: TenancyConfiguration | null;
  tenancy_id: TenancyId8;
  tenancy_name: TenancyName2;
  tenancy_revision: TenancyRevision;
  values: OverrideValues;
}
export interface BaselineVersion {
  based_on_id?: BasedOnId;
  content: BaselineContent;
  content_hash: ContentHash;
  created_at: CreatedAt1;
  created_by: CreatedBy;
  edit_revision: EditRevision;
  id: Id1;
  publication_mode?: PublicationMode;
  published_at?: PublishedAt;
  published_by?: PublishedBy;
  published_by_name?: PublishedByName;
  version_number: VersionNumber;
}
export interface BaselineContent {
  budget_currency: BudgetCurrency;
  budget_period?: BudgetPeriod;
  monthly_budget_amount: MonthlyBudgetAmount;
  policy_statements: PolicyStatements;
  quota_statements: QuotaStatements;
  tag_defaults?: TagDefaults;
  tag_namespace?: TagNamespace;
}
export interface TagDefault {
  key: Key;
  value: Value;
}
export interface TenancyConfiguration {
  baseline_version_id: BaselineVersionId;
  created_at: CreatedAt2;
  created_by: CreatedBy1;
  effective_hash: EffectiveHash;
  id: Id2;
  monthly_budget_override_amount?: MonthlyBudgetOverrideAmount;
  operation_id: OperationId2;
  policy_override_statements?: PolicyOverrideStatements;
  previous_id: PreviousId;
  quota_override_statements?: QuotaOverrideStatements;
  resolution_contract_version?: ResolutionContractVersion;
  revision_number: RevisionNumber;
  tenancy_id: TenancyId7;
}
export interface OverrideValues {
  monthly_budget_override_amount?: MonthlyBudgetOverrideAmount1;
  policy_override_statements?: PolicyOverrideStatements1;
  quota_override_statements?: QuotaOverrideStatements1;
}
export interface OverridePreviewRequest {
  context: OverrideContext;
  tenancy_id: TenancyId9;
  values: OverrideValues;
}
export interface OverrideContext {
  baseline_version_id: BaselineVersionId1;
  configuration_id: ConfigurationId;
  tenancy_revision: TenancyRevision1;
}
export interface ConfigurationPlanView {
  id: Id3;
  operation_id?: OperationId3;
  preview: ConfigurationPreview;
  revision: Revision;
  state: State7;
}
export interface ConfigurationPreview {
  baseline: BaselineVersion | null;
  blockers: Blockers;
  conflicts?: Conflicts;
  pending_count: PendingCount;
  preview_hash: PreviewHash;
  ready_count: ReadyCount;
  repair_expected?: RepairExpected;
  repair_observed?: RepairObserved;
  tenancy_id: TenancyId12;
}
export interface ConfigurationBlocker {
  code: Code;
  name: Name;
  operation_id?: OperationId4;
  tenancy_id: TenancyId10;
}
export interface OverrideConflict {
  old_baseline: BaselineVersion | null;
  overrides: OverrideValues;
  policy_choice?: PolicyChoice;
  policy_review: PolicyReview;
  quota_choice?: QuotaChoice;
  quota_review: QuotaReview;
  tenancy_id: TenancyId11;
  tenancy_name: TenancyName3;
}
export interface RepairExpected {
  [k: string]: string;
}
export interface RepairObserved {
  [k: string]: string | null;
}
export interface CreateConfigurationPlan {
  client_request_key: ClientRequestKey4;
  tenancy_id?: TenancyId13;
}
export interface SaveConfigurationReview {
  expected_revision: ExpectedRevision1;
  policy_choice?: PolicyChoice1;
  quota_choice?: QuotaChoice1;
  tenancy_id: TenancyId14;
}
export interface ConfigurationPreview1 {
  baseline: BaselineVersion | null;
  blockers: Blockers1;
  conflicts?: Conflicts1;
  pending_count: PendingCount1;
  preview_hash: PreviewHash1;
  ready_count: ReadyCount1;
  repair_expected?: RepairExpected1;
  repair_observed?: RepairObserved1;
  tenancy_id: TenancyId15;
}
export interface RepairExpected1 {
  [k: string]: string;
}
export interface RepairObserved1 {
  [k: string]: string | null;
}
export interface ConfigurationUpdate {
  client_request_key: ClientRequestKey5;
  override_context?: OverrideContext | null;
  override_mode?: OverrideMode;
  overrides?: OverrideValues | null;
  plan_id?: PlanId;
  preview_hash: PreviewHash2;
  repair_categories?: RepairCategories;
  tenancy_id?: TenancyId16;
}
export interface ConfigurationProgress {
  baseline: BaselineVersion;
  can_retry: CanRetry;
  change_kind?: ChangeKind;
  operation_id: OperationId5;
  state: State8;
  targets: Targets;
}
export interface ConfigurationTargetProgress {
  name: Name1;
  safe_code?: SafeCode2;
  state: State9;
  tenancy_id: TenancyId17;
  verified_at?: VerifiedAt;
}
export interface BaselineDirectory {
  configured: Configured;
  draft?: BaselineVersion | null;
  items?: Items1;
  latest?: BaselineVersion | null;
  page?: Page2;
  page_size?: PageSize2;
  pages?: Pages1;
  publication_available?: PublicationAvailable;
  selected?: BaselineVersion | null;
  total?: Total1;
}
export interface BaselineDraft {
  content: BaselineContent;
  content_hash: ContentHash1;
  created_at: CreatedAt3;
  created_by: CreatedBy2;
  edit_revision: EditRevision1;
  id: Id4;
  version_number: VersionNumber1;
}
export interface SaveBaselineDraft {
  based_on_id?: BasedOnId1;
  baseline_id?: BaselineId2;
  content: BaselineContent1;
  expected_revision?: ExpectedRevision2;
}
/**
 * Monthly budget must be a positive whole currency amount.
 */
export interface BaselineContent1 {
  budget_currency: BudgetCurrency;
  budget_period?: BudgetPeriod;
  monthly_budget_amount: MonthlyBudgetAmount;
  policy_statements: PolicyStatements;
  quota_statements: QuotaStatements;
  tag_defaults?: TagDefaults;
  tag_namespace?: TagNamespace;
}
export interface BaselineVersion1 {
  based_on_id?: BasedOnId2;
  content: BaselineContent;
  content_hash: ContentHash2;
  created_at: CreatedAt4;
  created_by: CreatedBy3;
  edit_revision: EditRevision2;
  id: Id5;
  publication_mode?: PublicationMode1;
  published_at?: PublishedAt1;
  published_by?: PublishedBy1;
  published_by_name?: PublishedByName1;
  version_number: VersionNumber2;
}
export interface BaselineQuery {
  baseline_id?: BaselineId3;
  page?: Page3;
  page_size?: PageSize3;
}
export interface PublishBaseline {
  baseline_id: BaselineId4;
  expected_revision: ExpectedRevision3;
}
export interface MappingSettings {
  available: Available;
  blockers: Blockers2;
  candidate: MappingCandidate | null;
  configured: Configured1;
  context: MappingContext;
  has_feed: HasFeed;
  roles: Roles;
  root_editable: RootEditable;
}
export interface MappingCandidate {
  root_email: RootEmail;
  root_name?: RootName;
  segments: Segments;
}
export interface MappingSegment {
  designee_emails?: DesigneeEmails;
  id?: Id6;
  label: Label;
  leader_email: LeaderEmail;
}
export interface MappingContext {
  applied_version_id?: AppliedVersionId;
  configuration_id?: ConfigurationId1;
  proposed_version_id?: ProposedVersionId;
  registry_revision?: RegistryRevision;
}
export interface MappingRole {
  email: Email;
  role: Role;
  segment_id: SegmentId;
  segment_name: SegmentName;
  status: Status;
}
export interface MappingRequest {
  candidate: MappingCandidate;
  change_root?: ChangeRoot;
  context: MappingContext;
}
export interface MappingApply {
  candidate: MappingCandidate;
  change_root?: ChangeRoot1;
  context: MappingContext;
  preview_token: PreviewToken;
}
export interface MappingPreview {
  affected_count: AffectedCount;
  blockers: Blockers3;
  candidate: MappingCandidate;
  changes: Changes;
  context: MappingContext;
  has_feed: HasFeed1;
  items: Items2;
  page: Page4;
  pages: Pages2;
  preview_token: PreviewToken1;
  roles: Roles1;
  root_before: RootBefore;
  root_name_before?: RootNameBefore;
  root_present: RootPresent;
  unassigned_count: UnassignedCount;
  unresolved_count: UnresolvedCount;
}
export interface MappingChange {
  after: MappingSegment | null;
  before: MappingSegment | null;
  segment_id: SegmentId1;
}
export interface MappingImpact {
  after_ancestry: AfterAncestry;
  after_designees: AfterDesignees;
  after_leader: AfterLeader;
  after_segment: AfterSegment;
  before_ancestry: BeforeAncestry;
  before_designees: BeforeDesignees;
  before_leader: BeforeLeader;
  before_segment: BeforeSegment;
  email: Email1;
  name: Name2;
  person_id: PersonId;
}
export interface TenancyDeletionCommand {
  client_request_key: ClientRequestKey6;
  confirm_deletion?: ConfirmDeletion;
  confirm_manager?: ConfirmManager;
  confirm_shared?: ConfirmShared;
  context: OrganizationContext;
  kind?: Kind;
  tenancy_id: TenancyId18;
}
export interface OrganizationContext {
  applied_version_id: AppliedVersionId1;
  configuration_id: ConfigurationId2;
  proposed_version_id: ProposedVersionId1;
  registry_revision: RegistryRevision1;
}
export interface TenancyDeletionPreview {
  context: OrganizationContext;
  manager_warning: ManagerWarning;
  people: People1;
  shared_warning: SharedWarning;
  tenancy: TenancyView;
}
export interface DeletionPerson {
  email: Email2;
  is_manager: IsManager;
  leaves_directory: LeavesDirectory;
  name: Name3;
  other_tenancy_count: OtherTenancyCount;
  person_id: PersonId1;
  role: Role1;
}
export interface TenancyView {
  baseline_version_id?: BaselineVersionId2;
  baseline_version_number?: BaselineVersionNumber2;
  cleanup_count: CleanupCount;
  configuration_check_stale?: ConfigurationCheckStale;
  configuration_check_state?: ConfigurationCheckState;
  configuration_checked_at?: ConfigurationCheckedAt;
  configuration_confirmed_issue_count?: ConfigurationConfirmedIssueCount;
  configuration_issue_count?: ConfigurationIssueCount;
  configuration_verified_at?: ConfigurationVerifiedAt;
  costs?: CostView1;
  created_at: CreatedAt5;
  desired_configuration_id?: DesiredConfigurationId;
  has_pending_operation?: HasPendingOperation;
  home_region: HomeRegion;
  id: Id7;
  kind: Kind1;
  last_verified_configuration_id?: LastVerifiedConfigurationId;
  leader_name: LeaderName;
  lob_name: LobName;
  manager_name: ManagerName;
  member_count: MemberCount;
  name: Name4;
  operation_completed_at?: OperationCompletedAt;
  operation_id: OperationId7;
  operation_state: OperationState;
  origin: Origin;
  override_categories?: OverrideCategories2;
  owner_email: OwnerEmail;
  owner_name: OwnerName;
  owner_person_id: OwnerPersonId;
  parent_tenancy_ocid: ParentTenancyOcid;
  provider_mode: ProviderMode3;
  required_users?: RequiredUsersSummary;
  status: Status1;
  tenancy_ocid: TenancyOcid;
  verified_at: VerifiedAt1;
  verified_baseline_version_id?: VerifiedBaselineVersionId;
  verified_baseline_version_number?: VerifiedBaselineVersionNumber;
}
export interface CostView1 {
  actual?: Actual1;
  actual_over_budget?: ActualOverBudget1;
  budget?: Budget1;
  can_refresh?: CanRefresh1;
  computed_at?: ComputedAt1;
  currency?: Currency1;
  cycle_facts?: BudgetCycleFacts | null;
  desired_budget?: DesiredBudget1;
  forecast?: Forecast1;
  forecast_over_budget?: ForecastOverBudget1;
  latest_failure?: LatestFailure1;
  minor_units?: MinorUnits1;
  operation_id?: OperationId6;
  pending?: Pending1;
  period_end?: PeriodEnd1;
  period_start?: PeriodStart1;
  retrieved_at?: RetrievedAt1;
  state?: State10;
}
export interface RequiredUsersSummary {
  automation?: UserPresenceView;
  checking?: Checking;
  recovery?: UserPresenceView;
  state?: State11;
}
export interface OnboardingCommand {
  action: Action;
  client_request_key: ClientRequestKey7;
  confirm_cleanup?: ConfirmCleanup;
  handoff?: OnboardingHandoff | null;
  revision: Revision1;
}
export interface OnboardingHandoff {
  activation_user_ocid?: ActivationUserOcid;
  bootstrap_user_ocid: BootstrapUserOcid;
  tenancy_ocid: TenancyOcid1;
}
export interface OnboardingView {
  administrator_email: AdministratorEmail;
  administrator_name: AdministratorName;
  available_actions: AvailableActions;
  baseline?: BaselineVersion | null;
  bootstrap_username: BootstrapUsername;
  can_act?: CanAct;
  checks: Checks;
  discovery: OnboardingDiscovery | null;
  email_contacts?: EmailContacts1 | null;
  expected_parent_tenancy_ocid: ExpectedParentTenancyOcid;
  issue_code?: IssueCode;
  operation_id: OperationId8;
  origin: Origin1;
  owner_name: OwnerName1;
  phase: Phase;
  public_key?: PublicKey;
  requested_home_region?: RequestedHomeRegion;
  requested_name?: RequestedName;
  revision: Revision2;
  state: State13;
  submitted_handoff: OnboardingHandoff | null;
  suggested_handoff: OnboardingHandoff;
  tenancy_id: TenancyId19;
}
export interface OnboardingCheck {
  key: Key1;
  label: Label1;
  state: State12;
  verified_at?: VerifiedAt2;
}
export interface OnboardingDiscovery {
  activation_scim_id: ActivationScimId;
  activation_user_ocid: ActivationUserOcid1;
  bootstrap_scim_id: BootstrapScimId;
  bootstrap_user_ocid: BootstrapUserOcid1;
  domain_ocid: DomainOcid1;
  home_region: HomeRegion1;
  name: Name5;
  organization_id: OrganizationId;
  parent_tenancy_ocid: ParentTenancyOcid1;
  tenancy_ocid: TenancyOcid2;
}
export interface EmailContacts1 {
  activation: EmailRoute;
  owner: EmailRoute;
  people?: People2;
}
export interface People2 {
  [k: string]: EmailRoute;
}
export interface OrganizationAction {
  action: Action1;
  client_request_key: ClientRequestKey8;
  compartment_name?: CompartmentName;
  confirm_destructive?: ConfirmDestructive;
  confirm_manager?: ConfirmManager1;
  confirm_no_associations?: ConfirmNoAssociations;
  confirm_shared?: ConfirmShared1;
  context: OrganizationContext;
  existing_compartment_ocid?: ExistingCompartmentOcid;
  former_owner_disposition?: FormerOwnerDisposition;
  home_region?: HomeRegion2;
  import_ocid?: ImportOcid;
  name?: Name6;
  operation_id?: OperationId9;
  parent_compartment_ocid?: ParentCompartmentOcid;
  partner_person_id?: PartnerPersonId;
  person_id: PersonId2;
  plan?: Plan;
  recipient_person_id?: RecipientPersonId1;
  review_id?: ReviewId;
  tenancy_id?: TenancyId20;
  tenancy_kind?: TenancyKind;
}
export interface AssociationChoice {
  action: Action2;
  association_id: AssociationId;
  former_owner_disposition?: FormerOwnerDisposition1;
  recipient_person_id?: RecipientPersonId;
}
export interface ActionReceipt {
  accepted_at: AcceptedAt1;
  operation_id: OperationId10;
  provider_mode: ProviderMode4;
  state: State14;
}
export interface PersonWorkflow {
  actions: Actions;
  associations: Associations;
  context: OrganizationContext;
  creation_regions?: CreationRegions;
  current_baseline?: BaselineVersion | null;
  directory_status: DirectoryStatus;
  email_contacts?: EmailContacts1 | null;
  is_manager: IsManager1;
  mapping_required?: MappingRequired;
  merge_partners: MergePartners;
  pending_operation_id: PendingOperationId3;
  person: PersonOption;
  provider_mode: ProviderMode5;
  review: ReviewView | null;
  shared_tenancies: SharedTenancies;
  source_present: SourcePresent;
  transfer_recipients: TransferRecipients;
}
export interface AssociationView {
  actions: Actions1;
  cleanup_required: CleanupRequired;
  compartment_name: CompartmentName1;
  compartment_ocid: CompartmentOcid;
  id: Id8;
  operation_id: OperationId11;
  person_id: PersonId3;
  role: Role2;
  status: Status2;
  tenancy_id: TenancyId21;
  tenancy_kind: TenancyKind1;
  tenancy_name: TenancyName4;
  tenancy_status: TenancyStatus1;
  user_ocid?: UserOcid1;
}
export interface CreationRegion {
  identifier: Identifier;
  name: Name7;
}
export interface PersonOption {
  email: Email3;
  id: Id9;
  name: Name8;
}
export interface ReviewView {
  category: Category1;
  data: Data;
  email: Email4;
  first_seen_at: FirstSeenAt;
  id: Id10;
  kind: Kind2;
  last_seen_at: LastSeenAt;
  name: Name9;
  operation_id: OperationId12;
  person_id: PersonId4;
  resolution: Resolution;
  resolved_at: ResolvedAt;
  status: Status3;
}
export interface Data {
  [k: string]: unknown;
}
export interface ReviewDirectory {
  actionable_count: ActionableCount;
  history_count: HistoryCount;
  informational_count?: InformationalCount;
  items: Items3;
  page: Page5;
  page_size: PageSize4;
  pages: Pages3;
  total: Total2;
}
export interface ReviewQuery {
  category?: Category2;
  direction?: Direction1;
  page?: Page6;
  page_size?: PageSize5;
  query?: Query1;
  sort?: Sort1;
}
export interface TenancyDirectory {
  can_refresh_costs?: CanRefreshCosts;
  costs_pending_count?: CostsPendingCount;
  individual_count: IndividualCount;
  issue_count: IssueCount2;
  items: Items4;
  latest_baseline_id?: LatestBaselineId;
  latest_baseline_version_number?: LatestBaselineVersionNumber;
  page: Page7;
  page_size: PageSize6;
  pages: Pages4;
  pending_count: PendingCount2;
  shared_count: SharedCount;
  total: Total3;
  total_tenancies: TotalTenancies;
}
export interface TenancyDetail {
  compartment_parents: CompartmentParents;
  configuration_operation_id?: ConfigurationOperationId;
  memberships: Memberships;
  onboarding_operation_id?: OnboardingOperationId;
  people: People3;
  tenancy: TenancyView;
}
export interface CompartmentOption {
  name: Name10;
  ocid: Ocid;
}
export interface TenancyQuery {
  direction?: Direction2;
  page?: Page8;
  page_size?: PageSize7;
  query?: Query2;
  shared_only?: SharedOnly;
  sort?: Sort2;
}
export interface OrganizationDirectory {
  absence_count: AbsenceCount;
  absence_eligible: AbsenceEligible;
  actionable_count?: ActionableCount1;
  applied_at: AppliedAt;
  configured: Configured2;
  employee_count: EmployeeCount;
  findings: Findings;
  history_count?: HistoryCount1;
  items: Items5;
  latest: OrganizationOutcome | null;
  page: Page9;
  page_size: PageSize8;
  pages: Pages5;
  pending_workflows?: PendingWorkflows;
  provider_mode?: ProviderMode6;
  server_time: ServerTime;
  source_as_of: SourceAsOf;
  test_reset_enabled?: TestResetEnabled;
  total: Total4;
  upload_enabled: UploadEnabled;
  workflows_enabled?: WorkflowsEnabled;
}
export interface OrganizationFinding {
  at: At;
  category: Category3;
  code: Code1;
  detail: Detail;
  email: Email5;
  employee_name: EmployeeName;
}
export interface EmployeeView {
  absence_review: AbsenceReview;
  directory_status?: DirectoryStatus1;
  email: Email6;
  full_name: FullName;
  id: Id11;
  leader_name: LeaderName1;
  lob_name: LobName1;
  manager_name: ManagerName1;
  pending_operation_id?: PendingOperationId4;
  pending_tenancy_count?: PendingTenancyCount;
  tenancy_count?: TenancyCount;
}
export interface OrganizationOutcome {
  diagnostics?: Diagnostics;
  original_state?: OriginalState;
  proposed_version_id?: ProposedVersionId2;
  revision_id?: RevisionId;
  snapshot_id: SnapshotId;
  state: State15;
}
export interface Diagnostic {
  affected_email?: AffectedEmail;
  code: Code2;
  fatal?: Fatal;
}
export interface OrganizationQuery {
  direction?: Direction3;
  include_removed?: IncludeRemoved;
  page?: Page10;
  page_size?: PageSize9;
  query?: Query3;
  sort?: Sort3;
}
export interface OrganizationOutcome1 {
  diagnostics?: Diagnostics1;
  original_state?: OriginalState1;
  proposed_version_id?: ProposedVersionId3;
  revision_id?: RevisionId1;
  snapshot_id: SnapshotId1;
  state: State16;
}
export interface BrandingView {
  display_name: DisplayName;
  icon_url: IconUrl;
  logo_url: LogoUrl;
}
export interface AdministratorDirectory {
  items: Items6;
  page: Page11;
  page_size: PageSize10;
  pages: Pages6;
  statistics: AdministratorStatistics;
  total: Total6;
}
export interface AdministratorView {
  authorization_revision: AuthorizationRevision;
  display_name: DisplayName1;
  email: Email7;
  id: Id12;
  identity_kind: IdentityKind;
  status: Status4;
}
export interface AdministratorStatistics {
  active: Active;
  protected_recovery: ProtectedRecovery;
  total: Total5;
}
export interface AdministratorQuery {
  direction?: Direction4;
  page?: Page12;
  page_size?: PageSize11;
  query?: Query4;
  sort?: Sort4;
}
export interface SessionView {
  display_name: DisplayName2;
  expires_at: ExpiresAt;
  workspace_id: WorkspaceId;
}
export interface OperationDirectory {
  attention_count?: AttentionCount;
  items: Items7;
  page: Page13;
  page_size: PageSize12;
  pages: Pages7;
  total: Total7;
}
export interface OperationSummary {
  accepted_at: AcceptedAt2;
  can_take_responsibility?: CanTakeResponsibility;
  completed_at: CompletedAt;
  guided_onboarding?: GuidedOnboarding;
  id: Id13;
  initiated_by: InitiatedBy;
  kind: Kind3;
  provider_mode?: ProviderMode7;
  responsibility_revision?: ResponsibilityRevision;
  responsible_administrator_id?: ResponsibleAdministratorId;
  responsible_administrator_name?: ResponsibleAdministratorName;
  result_tenancy_id?: ResultTenancyId;
  stage: Stage;
  state: State17;
  target_label?: TargetLabel;
  target_tenancy_ocid: TargetTenancyOcid;
  title?: Title;
  updated_at: UpdatedAt1;
}
export interface OperationDetail {
  events: Events;
  events_limited: EventsLimited;
  notifications?: Notifications;
  operation: OperationSummary;
  steps: Steps;
}
export interface OperationEventView {
  at: At1;
  kind: Kind4;
  safe_code: SafeCode3;
}
export interface NotificationSummary1 {
  attempts: Attempts1;
  created_at: CreatedAt6;
  event: Event1;
  id: Id14;
  last_attempt_at?: LastAttemptAt1;
  original_recipient: OriginalRecipient1;
  recipient: Recipient1;
  redirected: Redirected4;
  safe_code?: SafeCode4;
  state: State18;
  updated_at: UpdatedAt2;
}
export interface OperationStepView {
  attempt_number: AttemptNumber;
  safe_code: SafeCode5;
  state: State19;
  step_key: StepKey;
  verified_at: VerifiedAt3;
}
export interface OperationQuery {
  direction?: Direction5;
  page?: Page14;
  page_size?: PageSize13;
  query?: Query5;
  sort?: Sort5;
  state?: State20;
}
export interface Acceptance {
  accepted_at: AcceptedAt3;
  operation_id: OperationId13;
  state: State21;
}
export interface InspectionSubmission {
  client_request_key: ClientRequestKey9;
  tenancy_ocid: TenancyOcid3;
}
export interface SandboxCatalog {
  execution_paused: ExecutionPaused;
  provider_mode?: ProviderMode8;
  targets: Targets1;
}
export interface SandboxTarget {
  name: Name11;
  scenario: Scenario;
  tenancy_ocid: TenancyOcid4;
}
export interface AuditDirectory {
  items: Items8;
  page: Page15;
  page_size: PageSize14;
  pages: Pages8;
  total: Total8;
}
export interface AuditEntry {
  actor_name: ActorName;
  administrator_id: AdministratorId;
  administrator_name: AdministratorName1;
  at: At2;
  baseline_id?: BaselineId5;
  category: Category4;
  changes?: Changes1;
  id: Id15;
  kind: Kind5;
  operation_id: OperationId14;
  organization_subject_name?: OrganizationSubjectName;
  resources?: Resources;
  safe_code: SafeCode6;
  summary?: Summary;
}
export interface AuditResource {
  id: Id16;
  kind: Kind6;
  name: Name12;
}
export interface AuditQuery {
  category?: Category5;
  direction?: Direction6;
  from_at?: FromAt;
  page?: Page16;
  page_size?: PageSize15;
  query?: Query6;
  sort?: Sort6;
  to_at?: ToAt;
}
export interface AuditExportQuery {
  category?: Category6;
  direction?: Direction7;
  from_at?: FromAt1;
  query?: Query7;
  sort?: Sort7;
  to_at?: ToAt1;
}
