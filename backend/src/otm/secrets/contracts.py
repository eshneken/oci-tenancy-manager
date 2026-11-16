"""Implementation-neutral Vault read scope and redacted secret results; no SDK or local custody."""

from dataclasses import dataclass, field
from typing import Annotated

from pydantic import Field, SecretStr

from otm.contracts import Contract

# OCIDs are opaque identifiers; accept standard realm/region components, never URLs or whitespace.
VaultOcid = Annotated[str, Field(pattern=r"^ocid1\.vault\.oc[0-9]+\.[a-z0-9.-]{1,220}$")]
CompartmentOcid = Annotated[
    str, Field(pattern=r"^ocid1\.compartment\.oc[0-9]+\.[a-z0-9.-]{1,220}$")
]
SecretOcid = Annotated[str, Field(pattern=r"^ocid1\.vaultsecret\.oc[0-9]+\.[a-z0-9.-]{1,220}$")]


# One explicit application-custody boundary; a secret name never expands this authority.
class VaultReadScope(Contract):
    # Full OCI region name, at most63 characters; SDK construction rejects unknown regions.
    region: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,61}[0-9]$")]
    # Exact application Vault OCID; database-provisioning Vault is a separate custody boundary.
    vault_ocid: VaultOcid
    # Exact existing hosting compartment OCID; no descendant-compartment widening.
    compartment_ocid: CompartmentOcid


# Redact secret material in both container repr and the value's own string/JSON representation.
@dataclass(frozen=True, slots=True)
class VaultSecretValue:
    secret_ocid: str
    version_number: int
    value: SecretStr = field(repr=False)


# The boundary exposes no provider body, request URL, credential or raw SDK exception.
class VaultUnavailable(RuntimeError):
    pass
