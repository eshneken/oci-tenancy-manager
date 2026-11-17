ALTER TABLE public.otm_tenancy_membership ADD COLUMN imported_access JSONB;

ALTER TABLE public.otm_tenancy_membership ADD CONSTRAINT ck_membership_imported_access CHECK
(imported_access IS NULL OR (jsonb_typeof(imported_access)='object'
 AND imported_access->>'contract_version'='import-adoption-1'
 AND jsonb_typeof(imported_access->'identity')='object'
 AND imported_access->'identity'->>'user_ocid'=user_ocid
 AND length(imported_access->>'domain_ocid')>0) IS TRUE);

CREATE FUNCTION public.otm_imported_access_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NEW.imported_access IS DISTINCT FROM OLD.imported_access AND
    (OLD.status<>'pending' OR OLD.imported_access IS NOT NULL) THEN
   RAISE EXCEPTION 'accepted import identity provenance is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER otm_membership_imported_guard BEFORE UPDATE ON public.otm_tenancy_membership
FOR EACH ROW EXECUTE FUNCTION public.otm_imported_access_guard();
