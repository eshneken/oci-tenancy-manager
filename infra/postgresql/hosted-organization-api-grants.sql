-- Apply with the application table owner after migrations and creation of the runtime otm_api role.
-- Extends the baseline hosted authentication and audit grants for mapping and CSV intake.
GRANT SELECT, INSERT ON public.org_workspace, public.org_feed, public.org_person,
    public.org_version, public.org_member, public.org_recommendation TO otm_api;

GRANT UPDATE (configuration_id, configuration, proposed_version_id, applied_version_id)
    ON public.org_workspace TO otm_api;
GRANT UPDATE (state, diagnostics, proposed_version_id, applied_version_id)
    ON public.org_feed TO otm_api;
GRANT UPDATE (sealed) ON public.org_version TO otm_api;
GRANT UPDATE (directory_status, setup_required, setup_episode_id, removed_capture_at)
    ON public.org_person TO otm_api;
GRANT UPDATE (last_seen_at, version_id, status, resolved_at, resolution)
    ON public.org_recommendation TO otm_api;

-- Mapping revision checks and directory projection read existing lifecycle and baseline facts.
GRANT SELECT (id, workspace_id, state, kind, completed_at, effect_knowledge, current_intent_event_id)
    ON public.otm_operation TO otm_api;
GRANT SELECT ON public.otm_tenancy, public.otm_tenancy_membership TO otm_api;
GRANT SELECT (id, workspace_id, tenancy_id, policy_override_statements, quota_override_statements,
    monthly_budget_override_amount) ON public.otm_tenancy_configuration TO otm_api;
GRANT SELECT (id, workspace_id, version_number, published_at) ON public.otm_baseline_version TO otm_api;
