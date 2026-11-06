-- Permit exact permanent-user readback evidence in new onboarding graphs.

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_step_kind;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_step_kind CHECK ((step_key='inspect_target' AND command_kind='inspect_tenancy') OR (command_kind='organization_action' AND (step_key='apply_lifecycle' OR step_key ~ '^(remove_member_groups|delete_member_user):[0-9a-f-]{36}$')) OR (command_kind='onboarding' AND step_key IN ('handoff','inspect_bootstrap','establish_automation','verify_automation','configure_required','verify_required','retire_temporary','configure_baseline','verify_configured_access','capture_required_users')) OR (command_kind='configuration_update' AND step_key ~ '^configuration:[0-9a-f-]{36}$') OR (command_kind='configuration_check' AND step_key ~ '^configuration_check:[0-9a-f-]{36}$') OR (command_kind='cost_collection' AND step_key ~ '^cost:[0-9a-f-]{36}$'));
