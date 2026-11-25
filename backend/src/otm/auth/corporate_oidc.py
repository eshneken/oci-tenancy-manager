"""Server-side proof primitives for the Atlas Oracle OIDC pilot."""

import base64
import hashlib
import secrets
from urllib.parse import urlencode, urlsplit

import jwt
from pydantic import Field, SecretStr, field_validator

from otm.auth.corporate_enrollment import Guid
from otm.contracts import Contract, HttpsOrigin, Text

START_PATH = "/api/auth/sso/start"
CALLBACK_PATH = "/api/auth/sso/callback"
PKCE_S256 = "S256"


# Pin HTTPS provider origin, wire issuer and app identity independently of the Atlas namespace.
class OracleOidcBinding(Contract):
    # Canonical HTTPS origin of the provider endpoints, up to 256 characters.
    provider_origin: HttpsOrigin
    # Canonical HTTPS origin of Atlas, up to 256 characters, used to derive the exact callback.
    installation_origin: HttpsOrigin
    # Exact qualified HTTPS issuer, 1–256 characters, preserving the provider's trailing slash.
    wire_issuer: Text
    # Exact 1–256 character client audience, scoped to this installation.
    client_id: Text
    # Exact 1–256 character domain claim observed for the approved identity domain.
    domain_claim: Text
    # Exact 1–256 character signed provenance expected for the approved corporate IdP.
    corporate_idp: Text
    # Immutable OCI group GUID required in this installation's signed ID token.
    group: Guid

    # Accept the exact qualified issuer spelling, including the provider's trailing slash.
    @field_validator("wire_issuer")
    @classmethod
    def https_issuer(cls, value):
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(c.isspace() for c in value)
        ):
            raise ValueError("INVALID_ORACLE_OIDC_ISSUER")
        return value

    # Derive one callback from the trusted local or hosted installation HTTPS origin.
    def callback(self) -> str:
        return self.installation_origin + CALLBACK_PATH


# Send correlation values in the authorization query while keeping the PKCE verifier server-side.
class OidcAttemptMaterial(Contract):
    state: str = Field(repr=False)
    nonce: str = Field(repr=False)
    verifier: SecretStr

    # Generate independent high-entropy values for each authorization attempt.
    @classmethod
    def generate(cls):
        return cls(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            verifier=SecretStr(secrets.token_urlsafe(48)),
        )

    # Send only the S256 challenge to the pinned provider authorization endpoint.
    def authorization_url(self, binding: OracleOidcBinding) -> str:
        digest = hashlib.sha256(self.verifier.get_secret_value().encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return (
            binding.provider_origin
            + "/oauth2/v1/authorize?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": binding.client_id,
                    "redirect_uri": binding.callback(),
                    "scope": "openid get_groups",
                    "state": self.state,
                    "nonce": self.nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": PKCE_S256,
                }
            )
        )


# Return only the signed user and exact assignment group. Discard the remaining claims.
class VerifiedDomainLogin(Contract):
    guid: Guid
    group: Guid


# Accept the exact client and, for Oracle user assertions, only the already pinned wire issuer.
def oracle_audience_matches(audience, binding: OracleOidcBinding) -> bool:
    client, issuer = binding.client_id, binding.wire_issuer
    return audience in (client, [client], [client, issuer], [issuer, client]) and client != issuer


# Require a caller-supplied RSA key already trusted for the configured identity domain.
def verify_id_token(
    token: str, key, binding: OracleOidcBinding, attempt: OidcAttemptMaterial
) -> VerifiedDomainLogin:
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise ValueError("INVALID_ORACLE_ID_TOKEN")
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=binding.client_id,
            issuer=binding.wire_issuer,
            options={
                "require": [
                    "iss",
                    "sub",
                    "aud",
                    "exp",
                    "iat",
                    "nonce",
                    "user_id",
                    "user_tenantname",
                    "idp_name",
                    "groups",
                ]
            },
        )
        if (
            not claims["sub"]
            or not oracle_audience_matches(claims["aud"], binding)
            or claims.get("azp", binding.client_id) != binding.client_id
            or not secrets.compare_digest(claims["nonce"], attempt.nonce)
            or claims["user_tenantname"] != binding.domain_claim
            or claims["idp_name"] != binding.corporate_idp
            or type(claims["exp"]) is not int
            or type(claims["iat"]) is not int
            or claims["exp"] <= claims["iat"]
        ):
            raise ValueError("INVALID_ORACLE_ID_TOKEN")
        groups = claims["groups"]
        if not isinstance(groups, list) or not any(
            isinstance(group, dict) and group.get("id") == binding.group for group in groups
        ):
            raise ValueError("INVALID_ORACLE_ID_TOKEN")
        return VerifiedDomainLogin(guid=claims["user_id"], group=binding.group)
    except (jwt.PyJWTError, ValueError, TypeError):
        raise ValueError("INVALID_ORACLE_ID_TOKEN") from None
