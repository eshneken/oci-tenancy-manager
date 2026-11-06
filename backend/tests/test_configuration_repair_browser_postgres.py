"""Native repair UI qualification in its own owned installation, separate from check scenarios."""

import pytest
from test_configuration_drift_browser_postgres import configuration_browser
from test_sandbox_runtime_postgres import runtime

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Use a fresh module installation so another browser scenario cannot preconfigure this organization.
def test_configuration_repair_native_browser(runtime):
    configuration_browser(runtime, repair=True)
