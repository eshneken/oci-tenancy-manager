-- Earlier rows have no issued idle policy. Invalidate them instead of guessing active access.
ALTER TABLE public.otm_admin_session ADD COLUMN idle_timeout_seconds INTEGER;
UPDATE public.otm_admin_session SET idle_timeout_seconds=1800,
 revoked_at=COALESCE(revoked_at,CURRENT_TIMESTAMP);
ALTER TABLE public.otm_admin_session ALTER COLUMN idle_timeout_seconds SET NOT NULL;
ALTER TABLE public.otm_admin_session ADD CONSTRAINT ck_admin_session_idle CHECK(idle_timeout_seconds>=1);
