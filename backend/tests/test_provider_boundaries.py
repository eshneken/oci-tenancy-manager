"""Keep adapter selection explicit and shared scope checks independent of simulated identities."""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from otm.providers.configuration import require_configuration_target
from otm.providers.configuration_simulator import SimulatedConfigurationFacade


# Fresh imports must neither load a simulator/OCI adapter nor need a configured credential source.
def test_contract_imports_do_not_load_implementations(tmp_path):
    script = """
import importlib.abc
import sys

# Reject even attempted concrete-provider imports, including lazy transitive imports.
class RejectImplementations(importlib.abc.MetaPathFinder):
    # Leave neutral imports untouched while making accidental provider coupling fail loudly.
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'oci' or fullname.startswith('oci.') or fullname.endswith('_simulator'):
            raise AssertionError(fullname)
        return None

sys.meta_path.insert(0, RejectImplementations())
from otm.providers.baseline import BaselineQualifier, PublicationUnavailable
from otm.providers.budget import BudgetFacade, BudgetReadUnavailable
from otm.providers.configuration import ConfigurationFacade, configure_target, desired_objects
from otm.providers.lifecycle import (
    LifecycleFacade, LifecycleBlocked, MemberBinding, LifecycleCompletion,
)
from otm.providers.inspection import TenancyInspection
from otm.providers.required_user import RequiredUserInspection, RequiredUserProvider
from otm.providers.required_user_contracts import RequiredUserTarget
assert all(callable(item) for item in (
    BaselineQualifier, PublicationUnavailable, BudgetFacade, BudgetReadUnavailable,
    ConfigurationFacade, configure_target, desired_objects, LifecycleFacade,
    LifecycleBlocked, MemberBinding, LifecycleCompletion, TenancyInspection,
    RequiredUserInspection, RequiredUserProvider, RequiredUserTarget,
))
assert not any(name.endswith('_simulator') for name in sys.modules)
"""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OTM_", "OCI_", "PG"))
    }
    environment["OTM_APPLICATION_CONFIG"] = str(tmp_path / "does-not-exist.toml")
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# Scope validation is reusable by real adapters; only simulators restrict targets to fake OCIDs.
@pytest.mark.parametrize(
    ("parent", "organization", "child", "scope_valid", "simulation_valid"),
    [
        ("parent", "org", "ocid1.tenancy.oc1..otmsimchild", True, True),
        ("parent", "org", "ocid1.tenancy.oc1..examplechild", True, False),
        ("wrong", "org", "ocid1.tenancy.oc1..otmsimchild", False, False),
        ("parent", "wrong", "ocid1.tenancy.oc1..otmsimchild", False, False),
        ("parent", "org", "parent", False, False),
    ],
)
def test_shared_scope_and_simulator_identity_guards(
    parent, organization, child, scope_valid, simulation_valid
):
    policy = SimpleNamespace(parent_tenancy_ocid="parent", organization_id="org")
    target = SimpleNamespace(
        parent_tenancy_ocid=parent, organization_id=organization, tenancy_ocid=child
    )
    if scope_valid:
        require_configuration_target(target, policy)
    else:
        with pytest.raises(ValueError, match="^REGISTERED_CHILD_REQUIRED$"):
            require_configuration_target(target, policy)
    simulator = SimulatedConfigurationFacade(policy)
    if simulation_valid:
        simulator.require_target(target)
    else:
        with pytest.raises(ValueError, match="^REGISTERED_CHILD_REQUIRED$"):
            simulator.require_target(target)
