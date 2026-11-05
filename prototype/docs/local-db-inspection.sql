-- Active eight-table model. Filter by workspace: root-leader-sample or synthetic-lab.
SELECT * FROM otm_sample_demo_v2.org_workspace;

SELECT full_name, email, manager_name, manager_email, lob_id,
       accountable_leader_email, designee_emails, evidence, absence_review
FROM otm_sample_demo_v2.current_organization
WHERE workspace_id='root-leader-sample' ORDER BY full_name NULLS LAST, email;

SELECT c.email, c.full_name AS applied_name, p.full_name AS proposed_name,
       c.manager_email AS applied_manager, p.manager_email AS proposed_manager
FROM otm_sample_demo_v2.current_organization c
JOIN otm_sample_demo_v2.proposed_organization p
  ON p.workspace_id=c.workspace_id AND p.person_id=c.person_id
WHERE c.workspace_id='synthetic-lab' ORDER BY c.email;

SELECT person_email, field, before_value, after_value, status
FROM otm_sample_demo_v2.organization_reconciliation
WHERE workspace_id='synthetic-lab' ORDER BY created_at, id;

SELECT kind, target, status, reason
FROM otm_sample_demo_v2.pending_organization_reviews
WHERE workspace_id='synthetic-lab';

SELECT workspace_id, kind, actor, at, data
FROM otm_sample_demo_v2.audit_event ORDER BY at, id;

SELECT id, workspace_id, kind, base_version_id, feed_id, configuration_id, sealed
FROM otm_sample_demo_v2.org_version;

-- Full original immutable person evidence stays available alongside readable columns.
SELECT full_name, email, version_id, data
FROM otm_sample_demo_v2.org_member ORDER BY version_id, email;
