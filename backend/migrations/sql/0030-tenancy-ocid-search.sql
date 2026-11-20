-- Install the trusted extension for case-insensitive OCID substring indexing.
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;

CREATE INDEX ix_tenancy_ocid_search ON public.otm_tenancy
    USING gin (lower(tenancy_ocid) public.gin_trgm_ops);
