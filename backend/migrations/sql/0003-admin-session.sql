-- Opaque session metadata only; no SSO login or token issuance.

CREATE TABLE public.otm_admin_session (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	session_token_hash VARCHAR(64) NOT NULL, 
	issuer VARCHAR(256) NOT NULL, 
	subject VARCHAR(256) NOT NULL, 
	display_snapshot JSONB NOT NULL, 
	entitlement_reference VARCHAR(256) NOT NULL, 
	entitlement_revision UUID NOT NULL, 
	entitlement_checked_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	auth_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	provider_session_reference_hash VARCHAR(64), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_admin_session_token_hash UNIQUE (session_token_hash), 
	CONSTRAINT ck_admin_session_hash CHECK (session_token_hash ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_admin_session_provider_hash CHECK (provider_session_reference_hash IS NULL OR provider_session_reference_hash ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_admin_session_times CHECK (auth_time<=created_at AND created_at<expires_at AND last_seen_at>=created_at AND entitlement_checked_at<=created_at)
)

;
