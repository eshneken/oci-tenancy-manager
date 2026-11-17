"""Verified owner grants and immutable current expectations, separate from import provenance."""

from uuid import UUID

from otm.contracts import Contract, Text
from otm.tenancies.import_contracts import ExistingIdentity


# Exact provider readback links root policy to the administrator group and domain assignment.
class OwnerAdministration(Contract):
    association_id: UUID
    tenancy_ocid: Text
    domain_ocid: Text
    identity: ExistingIdentity
    administrator_group_id: Text
    administrator_role_id: Text
    root_policy_id: Text
    policy_group_id: Text
    policy_scope_ocid: Text
    manage_all_resources: bool
    domain_administrator: bool
    authorized: bool
    supported: bool
    complete: bool
