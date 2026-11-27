"""Verify the protected environment handoff with an owned key and synthetic OAuth app."""

import base64
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nacl.public import PrivateKey, SealedBox

SPEC = importlib.util.spec_from_file_location(
    "seal_inputs", Path(__file__).resolve().parents[1] / "seal_inputs.py"
)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


# Real sealed boxes and a fake OCI response exercise the complete pre-Terraform credential boundary.
class SealInputsTests(unittest.TestCase):
    # Bind every lookup to one fresh recipient and a synthetic exact OAuth client.
    def setUp(self):
        self.private = PrivateKey.generate()
        self.query = {
            "environment": "production",
            "repository": "example/project",
            "key_id": "123",
            "public_key": base64.b64encode(bytes(self.private.public_key)).decode(),
            "target": json.dumps({"environment": "production"}),
            "settings_file": "sample.json",
            "oci_auth": "SecurityToken",
            "oci_profile": "SYNTHETIC",
            "domain_url": "https://idcs-synthetic.identity.oraclecloud.com",
            "app_id": "a" * 32,
            "client_id": "synthetic-client",
            "compartment_ocid": "synthetic-compartment",
        }
        self.app = {
            "id": "a" * 32,
            "name": "synthetic-client",
            "display-name": "otm-github-production",
            "client-type": "confidential",
            "is-o-auth-client": True,
            "is-o-auth-resource": False,
            "is-login-target": False,
            "trust-scope": "Explicit",
            "allowed-scopes": None,
            "granted-app-roles": None,
            "allowed-grants": ["client_credentials"],
            "client-secret": "synthetic-exchange-value",
        }
        self.settings = {
            "inputs": {"atlas_sso": {"corporate_idp_id": "example-idp"}},
            "allowed_source_cidrs": "synthetic-allowlist",
            "worker_cloud_init": "#!/bin/bash\ntrue\n",
        }

    # Verify exact-client reads, byte-preserving sealing, stable triggers and fresh nonces.
    def test_round_trip(self):
        with (
            patch.object(helper, "read_settings", return_value=self.settings),
            patch.object(
                helper, "invoke", return_value=json.dumps({"data": self.app}).encode()
            ) as invoke,
        ):
            first = helper.seal(self.query)
            second = helper.seal(self.query)
        command = invoke.call_args.args[0]
        self.assertEqual(command[0], "oci")
        self.assertIn(
            ["identity-domains", "app", "get", "--app-id", "a" * 32],
            [command[i : i + 5] for i in range(len(command))],
        )
        self.assertNotIn(self.app["client-secret"], json.dumps(first))
        self.assertEqual(first["input_digest"], second["input_digest"])
        self.assertNotEqual(
            first["OTM_INFRA_CLIENT_SECRET"], second["OTM_INFRA_CLIENT_SECRET"]
        )
        box = SealedBox(self.private)
        decoded = {
            k: box.decrypt(base64.b64decode(v)).decode()
            for k, v in first.items()
            if k != "input_digest"
        }
        self.assertEqual(decoded["OTM_INFRA_CLIENT_SECRET"], self.app["client-secret"])
        self.assertEqual(
            decoded["OTM_WORKER_CLOUD_INIT"], self.settings["worker_cloud_init"]
        )
        self.assertEqual(
            json.loads(decoded["OTM_INFRASTRUCTURE_INPUTS_JSON"])["target"],
            {"environment": "production"},
        )

    # Legacy read projection excludes credentials even if OCI unexpectedly returns extra fields.
    def test_legacy_exchange_metadata(self):
        query = self.query | {"environment": "development", "oci_auth": "APIKey"}
        app = self.app | {
            "display-name": "otm-github-development",
            "active": True,
        }
        with patch.object(
            helper, "invoke", return_value=json.dumps({"data": app}).encode()
        ) as invoked:
            self.assertEqual(
                helper.development_exchange_metadata(query),
                {"name": app["name"], "id": app["id"]},
            )
        self.assertEqual(
            invoked.call_args.args[0][-1],
            "id,name,displayName,allowedGrants,clientType,isOAuthClient,isOAuthResource,"
            "isLoginTarget,trustScope,allowedScopes,grantedAppRoles,active",
        )
        with (
            patch.object(
                helper,
                "invoke",
                return_value=json.dumps({"data": app | {"active": False}}).encode(),
            ),
            self.assertRaisesRegex(ValueError, "ACTIVE_EXCHANGE_APP_REQUIRED"),
        ):
            helper.development_exchange_metadata(query)

    # Fresh development emits an empty pin and does not contact OCI from the settings reader.
    def test_no_development_group_adoption(self):
        settings = {"inputs": {"atlas_sso": {}}}
        with (
            patch.object(helper, "read_settings", return_value=settings),
            patch.object(helper, "invoke") as invoke,
        ):
            self.assertEqual(
                helper.development_group_adoption_pin(self.query), {"ocid": ""}
            )
            invoke.assert_not_called()

    # Emit one validated OCID without exposing any other protected settings.
    def test_development_group_adoption_pin(self):
        group_ocid = "ocid1.group.oc1..syntheticatlas"
        settings = {
            "inputs": {
                "atlas_sso": {
                    "adopt_group_ocid": group_ocid,
                    "corporate_idp_id": "a" * 32,
                }
            }
        }
        with (
            patch.object(helper, "read_settings", return_value=settings) as read,
            patch.object(helper, "invoke") as invoke,
        ):
            self.assertEqual(
                helper.development_group_adoption_pin(self.query), {"ocid": group_ocid}
            )
            read.assert_called_once_with(self.query["settings_file"])
            invoke.assert_not_called()

    # Refuse file shapes or identifiers that cannot be verified by the exact native group read.
    def test_invalid_development_group_adoption_pin(self):
        for text in (
            "",
            None,
            "ocid1.group.oc1..bad'name",
            "ocid1.user.oc1..synthetic",
        ):
            with (
                self.subTest(value=text),
                patch.object(
                    helper,
                    "read_settings",
                    return_value={"inputs": {"atlas_sso": {"adopt_group_ocid": text}}},
                ),
                self.assertRaisesRegex(ValueError, "EXACT_ADOPTION_GROUP_REQUIRED"),
            ):
                helper.development_group_adoption_pin(self.query)

    # Refuse input-file target overrides before reaching the sensitive OCI GetApp projection.
    def test_wrong_source_target(self):
        self.settings["inputs"]["target"] = {"environment": "staging"}
        with (
            patch.object(helper, "read_settings", return_value=self.settings),
            patch.object(helper, "invoke") as invoke,
        ):
            with self.assertRaisesRegex(ValueError, "PRIVATE_CONFIGURATION_REQUIRED"):
                helper.seal(self.query)
            invoke.assert_not_called()

    # Each immutable binding and restricted grant must match before sealing the returned credential.
    def test_reject_wrong_oci_app(self):
        for key, value in {
            "id": "b" * 32,
            "name": "other",
            "display-name": "otm-github-staging",
            "client-type": "public",
            "allowed-scopes": ["synthetic"],
            "granted-app-roles": [{"value": "synthetic"}],
            "allowed-grants": ["password"],
            "client-secret": "bad\nvalue",
        }.items():
            with (
                self.subTest(key=key),
                patch.object(
                    helper,
                    "invoke",
                    return_value=json.dumps({"data": self.app | {key: value}}).encode(),
                ),
                self.assertRaisesRegex(ValueError, "EXACT_EXCHANGE_APP_REQUIRED"),
            ):
                helper.exchange_secret(self.query)

    # A compromised or verbose OCI CLI must not inherit operator GitHub or Terraform credentials.
    def test_oci_process_environment(self):
        environment = {
            "PATH": "/example/bin",
            "OCI_CLI_CONFIG_FILE": "/example/config",
            "OCI_RESOURCE_PRINCIPAL_VERSION": "2.2",
            "GITHUB_TOKEN": "synthetic",
            "GH_TOKEN": "synthetic",
            "TF_VAR_secret": "synthetic",
            "GH_ENTERPRISE_TOKEN": "synthetic",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "synthetic",
            "OCI_CLI_DEBUG": "1",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(
                helper.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(["oci"], 0, b"ok"),
            ) as called,
        ):
            helper.invoke(["oci"])
        self.assertEqual(
            set(called.call_args.kwargs["env"]),
            {"PATH", "OCI_CLI_CONFIG_FILE", "OCI_RESOURCE_PRINCIPAL_VERSION"},
        )

    # Only the owner may supply a direct regular file beneath the designated private directory.
    def test_private_file(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(helper, "PRIVATE_DIR", Path(directory)),
        ):
            fixture = Path(directory) / "sample.json"
            fixture.write_text(json.dumps(self.settings))
            fixture.chmod(0o600)
            self.assertEqual(helper.read_settings(fixture.name), self.settings)
            fixture.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "PRIVATE_CONFIGURATION_REQUIRED"):
                helper.read_settings(fixture.name)
            with self.assertRaisesRegex(ValueError, "PRIVATE_CONFIGURATION_REQUIRED"):
                helper.read_settings("../sample.json")
            alias = Path(directory) / "alias.json"
            alias.symlink_to(fixture)
            with self.assertRaises(OSError):
                helper.read_settings(alias.name)
