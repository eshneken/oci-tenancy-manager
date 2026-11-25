"""Exercise exact provider metadata, PKCE exchange and key selection without OCI calls."""

import json
from unittest.mock import Mock
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from test_corporate_oidc import GUID, binding, claims_for, signing_key

from otm.auth.corporate_exchange import (
    AUTHORIZE,
    DISCOVERY,
    EXCHANGE_PATH,
    KEYS,
    OracleCodeExchange,
)
from otm.auth.corporate_oidc import OidcAttemptMaterial

__all__ = ["binding", "signing_key"]


# Verify the exact endpoints, credential isolation and signed GUID on the synthetic happy path.
@pytest.mark.parametrize(
    "fault", [None, "wrong_host", "wrong_port", "redirect", "wrong_key", "oversized"]
)
@pytest.mark.parametrize("metadata_port", ["", ":443"])
def test_oracle_exchange_pins_all_endpoints_and_selects_one_key(
    binding, signing_key, fault, metadata_port
):
    attempt = OidcAttemptMaterial.generate()
    token = jwt.encode(
        claims_for(binding, attempt), signing_key, algorithm="RS256", headers={"kid": "k1"}
    )
    key = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key())
    base = binding.provider_origin
    metadata_base = base + metadata_port
    requests = []

    # Respond only to known paths and verify that authorizing secrets never reach discovery or JWKS.
    def serve(request):
        path = request.url.path
        assert request.url.host == "identity-domain.example.test"
        requests.append(path)
        if path == DISCOVERY:
            assert "authorization" not in request.headers
            return httpx.Response(
                200,
                json={
                    "issuer": binding.wire_issuer,
                    "authorization_endpoint": metadata_base + AUTHORIZE,
                    "token_endpoint": (
                        {
                            "wrong_host": "https://unexpected.example.test",
                            "wrong_port": base + ":444",
                        }.get(fault, metadata_base)
                    )
                    + EXCHANGE_PATH,
                    "jwks_uri": metadata_base + KEYS,
                    "code_challenge_methods_supported": ["S256"],
                },
            )
        if path == EXCHANGE_PATH:
            assert request.method == "POST"
            assert request.headers["authorization"].startswith("Basic ")
            assert parse_qs(request.content.decode()) == {
                "grant_type": ["authorization_code"],
                "code": ["code"],
                "redirect_uri": [binding.callback()],
                "code_verifier": [attempt.verifier.get_secret_value()],
            }
            if fault == "redirect":
                return httpx.Response(302, headers={"location": "https://unexpected.example.test"})
            if fault == "oversized":
                return httpx.Response(200, content=b"x" * 65537)
            return httpx.Response(200, json={"id_token": token})
        assert path == KEYS and "authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "keys": [
                    {
                        **json.loads(key),
                        "kid": "wrong" if fault == "wrong_key" else "k1",
                        "use": "sig",
                    }
                ]
            },
        )

    secret = Mock(return_value="synthetic-development-secret")
    exchange = OracleCodeExchange(binding, secret, transport=httpx.MockTransport(serve))
    if fault:
        with pytest.raises(ValueError, match="^ORACLE_OIDC_EXCHANGE_FAILED$"):
            exchange.exchange("code", attempt)
        if fault in {"wrong_host", "wrong_port"}:
            secret.assert_not_called()
            assert requests == [DISCOVERY]
        elif fault in ("redirect", "oversized"):
            assert requests == [DISCOVERY, EXCHANGE_PATH]
    else:
        assert exchange.exchange("code", attempt).guid == GUID
        secret.assert_called_once()
        assert requests == [DISCOVERY, EXCHANGE_PATH, KEYS]
