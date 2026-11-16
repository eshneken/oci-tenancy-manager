"""Nonsecret, explicit platform SDK identity selection; no credentials or provider side effects."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from otm.contracts import Contract


# Cloud identity is independent of laptop/hosted serving and never inferred from available files.
class OciSettings(Contract):
    # Explicit platform authentication; API keys are laptop-only, workload identity hosted-only.
    auth_method: Literal["api_key_profile", "oke_workload_identity"]
    # Full OCI region name, 3–63 characters; client creation also requires a known SDK region.
    region: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,61}[0-9]$")]
    # Expected platform credential tenancy, not an authorization grant over any managed child.
    tenancy_ocid: Annotated[str, Field(pattern=r"^ocid1\.tenancy\.oc[0-9]+\.[a-z0-9.-]{1,220}$")]
    # Explicit private OCI config path for API keys; absolute or ~/ only, at most4096 characters.
    config_file: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    # Named profile,1–64 simple characters; DEFAULT and inherited credentials are forbidden.
    profile: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")] | None = None

    # A missing local profile never selects DEFAULT, and hosted settings never carry local files.
    @model_validator(mode="after")
    def coherent_authentication(self):
        if self.auth_method == "api_key_profile":
            if (
                self.config_file is None
                or not self.config_file.startswith(("/", "~/"))
                or self.profile is None
                or self.profile.casefold() == "default"
            ):
                raise ValueError("EXPLICIT_OCI_PROFILE_REQUIRED")
        elif self.config_file is not None or self.profile is not None:
            raise ValueError("HOSTED_OCI_PROFILE_FORBIDDEN")
        return self
