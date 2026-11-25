"""Oracle OIDC attempt parameters and cryptographic verification with synthetic tokens."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from otm.auth.corporate_oidc import OidcAttemptMaterial, OracleOidcBinding, verify_id_token

GUID = "e" * 32
GROUP = "b" * 32


# Keep signing keys and provider values entirely synthetic while verifying actual RSA signatures.
@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


# Bind a shared wire issuer to the exact development client, domain and corporate provider.
@pytest.fixture
def binding():
    return OracleOidcBinding(
        provider_origin="https://identity-domain.example.test",
        installation_origin="https://127.0.0.1:8445",
        wire_issuer="https://identity.example.test/",
        client_id="development-client",
        domain_claim="development-domain",
        corporate_idp="corporate-saml",
        group=GROUP,
    )


# Construct signed claim inputs with exp/iat in the valid time window for each test.
def claims_for(binding, attempt):
    now = int(datetime.now(UTC).timestamp())
    return {
        "iss": binding.wire_issuer,
        "aud": [binding.client_id],
        "sub": "original-login",
        "user_id": GUID,
        "iat": now - 2,
        "exp": now + 300,
        "nonce": attempt.nonce,
        "idp_name": binding.corporate_idp,
        "user_tenantname": binding.domain_claim,
        "groups": [{"id": GROUP, "name": "synthetic-development-users"}],
    }


# Derive the exact HTTPS callback and use RFC 7636 S256 without sending the verifier.
def test_authorization_url_uses_exact_callback_with_s256(binding):
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    attempt = OidcAttemptMaterial(state="one", nonce="two", verifier=SecretStr(verifier))
    url = urlsplit(attempt.authorization_url(binding))
    assert url.hostname == "identity-domain.example.test" and url.path == "/oauth2/v1/authorize"
    assert parse_qs(url.query) == {
        "response_type": ["code"],
        "client_id": ["development-client"],
        "redirect_uri": ["https://127.0.0.1:8445/api/auth/sso/callback"],
        "scope": ["openid get_groups"],
        "state": ["one"],
        "nonce": ["two"],
        "code_challenge": ["E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"],
        "code_challenge_method": ["S256"],
    }
    assert verifier not in url.query
    assert OidcAttemptMaterial.generate().state != OidcAttemptMaterial.generate().state


# A username rename leaves the signed GUID stable. A recreated account receives a new subject.
def test_jwt_binds_signed_guid_not_login_name(binding, signing_key):
    attempt = OidcAttemptMaterial.generate()
    original = claims_for(binding, attempt)
    for claims, guid in (
        (original, GUID),
        ({**original, "sub": "renamed-login"}, GUID),
        ({**original, "user_id": "f" * 32}, "f" * 32),
    ):
        token = jwt.encode(claims, signing_key, algorithm="RS256")
        proof = verify_id_token(token, signing_key.public_key(), binding, attempt)
        assert proof.guid == guid and proof.group == GROUP


# Accept the pinned issuer beside the client in either order and reject unexpected audiences.
@pytest.mark.parametrize(
    ("audience", "azp", "valid"),
    [
        (["client", "issuer"], None, True),
        (["issuer", "client"], "client", True),
        (["client", "issuer"], "other", False),
        (["issuer", "other"], "client", False),
        (["client", "issuer", "other"], "client", False),
        (["client", "issuer", "issuer"], "client", False),
        (["client", "issuer_without_slash"], "client", False),
    ],
)
def test_oracle_token_only_allows_pinned_issuer_as_additional_audience(
    binding, signing_key, audience, azp, valid
):
    attempt = OidcAttemptMaterial.generate()
    values = {
        "client": binding.client_id,
        "issuer": binding.wire_issuer,
        "issuer_without_slash": binding.wire_issuer.rstrip("/"),
        "other": "other",
    }
    claims = {**claims_for(binding, attempt), "aud": [values[name] for name in audience]}
    if azp is not None:
        claims["azp"] = values[azp]
    token = jwt.encode(claims, signing_key, algorithm="RS256")
    if valid:
        assert verify_id_token(token, signing_key.public_key(), binding, attempt).guid == GUID
    else:
        with pytest.raises(ValueError, match="^INVALID_ORACLE_ID_TOKEN$"):
            verify_id_token(token, signing_key.public_key(), binding, attempt)


# Deny native sign-in, wrong target/audience/issuer, mismatched nonce and unqualified identity.
@pytest.mark.parametrize(
    "update",
    [
        {"idp_name": "UserNamePassword"},
        {"azp": "staging-client"},
        {"aud": ["staging-client"]},
        {"aud": ["development-client", "staging-client"]},
        {"user_tenantname": "other-domain"},
        {"iss": "https://other.example.test/"},
        {"nonce": "different"},
        {"user_id": "person@example.test"},
        {"exp": 1},
        {"nonce": ["not-a-string"]},
        {"groups": []},
        {"groups": {"id": GROUP}},
        {"groups": [GROUP]},
        {"groups": [{"name": "synthetic-development-users", "id": "d" * 32}]},
        {"groups": [{"value": GROUP}]},
        {"groups": [{"name": GROUP}]},
    ],
)
def test_oracle_token_rejects_wrong_authority(binding, signing_key, update):
    attempt = OidcAttemptMaterial.generate()
    token = jwt.encode({**claims_for(binding, attempt), **update}, signing_key, algorithm="RS256")
    with pytest.raises(ValueError, match="^INVALID_ORACLE_ID_TOKEN$"):
        verify_id_token(token, signing_key.public_key(), binding, attempt)


# Reject an unsigned token, missing provenance, a wrong signature and invalid issuer config.
def test_oracle_token_needs_pinned_signature_and_claims(binding, signing_key):
    attempt = OidcAttemptMaterial.generate()
    values = claims_for(binding, attempt)
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    corrupt = jwt.encode(values, wrong_key, algorithm="RS256")
    unsigned = jwt.encode(values, "", algorithm="none")
    values.pop("idp_name")
    incomplete = jwt.encode(values, signing_key, algorithm="RS256")
    for token in (corrupt, unsigned, incomplete, ""):
        with pytest.raises(ValueError, match="^INVALID_ORACLE_ID_TOKEN$"):
            verify_id_token(token, signing_key.public_key(), binding, attempt)
    with pytest.raises(ValueError):
        OracleOidcBinding.model_validate({**binding.model_dump(), "wire_issuer": "http://id.test"})
