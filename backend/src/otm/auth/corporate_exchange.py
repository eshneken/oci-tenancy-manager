"""Bounded Oracle authorization-code exchange for an explicitly configured installation."""

import json
from urllib.parse import quote_plus, urlsplit

import httpx
import jwt

from otm.auth.corporate_oidc import OidcAttemptMaterial, OracleOidcBinding, verify_id_token

AUTHORIZE = "/oauth2/v1/authorize"
EXCHANGE_PATH = "/oauth2/v1/token"
KEYS = "/admin/v1/SigningCert/jwk"
DISCOVERY = "/.well-known/openid-configuration"
MAX_DOCUMENT = 65536


# Keep provider transport/credentials injectable for synthetic testing and late secret loading.
class OracleCodeExchange:
    # Resolve the secret only after a browser callback passes its attempt checks.
    def __init__(self, binding: OracleOidcBinding, secret, *, transport=None):
        self.binding, self.secret, self.transport = binding, secret, transport

    # Reconfirm exact discovery endpoints before sending the code or credential anywhere.
    def exchange(self, code: str, attempt: OidcAttemptMaterial):
        base = self.binding.provider_origin
        try:
            with httpx.Client(
                transport=self.transport, follow_redirects=False, trust_env=False, timeout=5.0
            ) as client:
                discovery = document(client, "GET", base + DISCOVERY)
                endpoints = {
                    "authorization_endpoint": AUTHORIZE,
                    "token_endpoint": EXCHANGE_PATH,
                    "jwks_uri": KEYS,
                }
                metadata_origins = (base, base + ":443") if urlsplit(base).port is None else (base,)
                if (
                    discovery.get("issuer") != self.binding.wire_issuer
                    # OCI discovery can spell the pinned HTTPS endpoint with an explicit :443.
                    or any(
                        discovery.get(name)
                        not in tuple(origin + path for origin in metadata_origins)
                        for name, path in endpoints.items()
                    )
                    or "S256" not in discovery.get("code_challenge_methods_supported", ())
                ):
                    raise ValueError("ORACLE_OIDC_METADATA_MISMATCH")
                secret = self.secret()
                if not isinstance(secret, str) or not 1 <= len(secret) <= 4096:
                    raise ValueError("ORACLE_OIDC_SECRET_UNAVAILABLE")
                response = document(
                    client,
                    "POST",
                    base + EXCHANGE_PATH,
                    auth=(quote_plus(self.binding.client_id), quote_plus(secret)),
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self.binding.callback(),
                        "code_verifier": attempt.verifier.get_secret_value(),
                    },
                )
                token = response.get("id_token")
                if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                    raise ValueError("ORACLE_ID_TOKEN_MISSING")
                header = jwt.get_unverified_header(token)
                kid = header.get("kid")
                if (
                    header.get("alg") != "RS256"
                    or not isinstance(kid, str)
                    or not 1 <= len(kid) <= 256
                ):
                    raise ValueError("ORACLE_ID_TOKEN_KEY_REQUIRED")
                jwks = document(client, "GET", base + KEYS)
            matches = [
                key
                for key in jwks.get("keys", ())
                if key.get("kid") == kid
                and key.get("kty") == "RSA"
                and key.get("use", "sig") == "sig"
                and key.get("alg", "RS256") == "RS256"
            ]
            if len(matches) != 1:
                raise ValueError("ORACLE_ID_TOKEN_KEY_REQUIRED")
            key = jwt.PyJWK.from_dict(matches[0], algorithm="RS256").key
            return self._verify(token, key, attempt)
        except Exception:
            raise ValueError("ORACLE_OIDC_EXCHANGE_FAILED") from None

    # Keep signed identity verification distinct from exchange and key selection.
    def _verify(self, token, key, attempt):
        return verify_id_token(token, key, self.binding, attempt)


# Bound public metadata and token responses and reject redirects before reading their body.
def document(client, method, url, **kwargs):
    with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes(chunk_size=8192):
            if len(data) + len(chunk) > MAX_DOCUMENT:
                raise ValueError("ORACLE_OIDC_RESPONSE_TOO_LARGE")
            data.extend(chunk)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("ORACLE_OIDC_RESPONSE_INVALID")
    return value
