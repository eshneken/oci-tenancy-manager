ALTER TABLE public.otm_administrator ADD COLUMN group_cleanup_complete boolean NOT NULL DEFAULT false;
ALTER TABLE public.otm_administrator ADD CONSTRAINT ck_administrator_cleanup_revoked CHECK (NOT group_cleanup_complete OR (status = 'revoked' AND identity_kind = 'corporate_sso'));
