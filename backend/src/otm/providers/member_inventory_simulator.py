"""Private persistent fake-cloud observations; no registry-derived success or actual OCI calls."""

import hashlib
import json
import os
from pathlib import Path

from pydantic import model_validator

from otm.contracts import Contract, Text
from otm.secrets.private_json import PrivateJsonRecords
from otm.tenancies.import_contracts import ExistingIdentity


# Tombstones survive restart and retain the exact account scope even after identity deletion.
class MemberObservation(Contract):
    tenancy_ocid: Text
    user_ocid: Text
    domain_ocid: Text | None = None
    user: bool = True
    groups: bool = True
    identity: ExistingIdentity | None = None
    root_policy_id: Text | None = None
    policy_group_id: Text | None = None
    policy_scope_ocid: Text | None = None
    manage_all_resources: bool = False
    domain_administrator: bool = False

    # A retained identity must remain scoped to its exact account and known domain.
    @model_validator(mode="after")
    def scoped_identity(self):
        if self.identity is not None and (
            self.identity.user_ocid != self.user_ocid or self.domain_ocid is None
        ):
            raise ValueError("MEMBER_OBSERVATION_IDENTITY_INVALID")
        return self


# The existing guarded file implementation supplies scoped locks, bounded reads and atomic fsync.
class MemberInventory:
    # An absent path selects in-memory unit simulation; laptop composition supplies one private
    # root.
    def __init__(self, directory=None):
        self.records = PrivateJsonRecords(Path(directory)) if directory is not None else None
        self.memory = {}

    # File names contain only hashes of verified provider scope, never employee data or supplied
    # paths.
    def key(self, tenancy, user=None):
        return hashlib.sha256(tenancy.encode()).hexdigest()[:32] + (
            "-" + hashlib.sha256(user.encode()).hexdigest()[:32] if user else ""
        )

    # Read all this child's complete records under its shared write lock; corruption fails closed.
    def read(self, tenancy):
        if self.records is None:
            return {key: value.copy() for key, value in self.memory.items() if key[0] == tenancy}
        name = self.key(tenancy)
        result = {}
        with self.records.locked(name) as directory:
            for filename in os.listdir(directory):
                if not filename.startswith(name + "-") or not filename.endswith(".json"):
                    continue
                row = MemberObservation.model_validate_json(
                    json.dumps(self.records.read(directory, filename))
                )
                if (
                    row.tenancy_ocid != tenancy
                    or filename != self.key(tenancy, row.user_ocid) + ".json"
                ):
                    raise ValueError("MEMBER_OBSERVATION_SCOPE_INVALID")
                if row.identity is not None and row.identity.user_ocid != row.user_ocid:
                    raise ValueError("MEMBER_OBSERVATION_IDENTITY_INVALID")
                result[(tenancy, row.user_ocid)] = row.model_dump(
                    mode="json", exclude={"tenancy_ocid", "user_ocid"}
                )
        return result

    # Persist only one exact account and never turn a deleted account back into an active identity.
    def write(self, tenancy, user, value):
        row = MemberObservation.model_validate_json(
            json.dumps(dict(value, tenancy_ocid=tenancy, user_ocid=user))
        )
        if self.records is None:
            previous = self.memory.get((tenancy, user))
            if previous and not previous["user"] and row.user:
                raise ValueError("MEMBER_DELETED")
            self.memory[(tenancy, user)] = row.model_dump(
                mode="json", exclude={"tenancy_ocid", "user_ocid"}
            )
            return
        with self.records.locked(self.key(tenancy)) as directory:
            filename = self.key(tenancy, user) + ".json"
            try:
                previous = MemberObservation.model_validate_json(
                    json.dumps(self.records.read(directory, filename))
                )
            except FileNotFoundError:
                previous = None
            if previous is not None and (
                previous.tenancy_ocid != tenancy or previous.user_ocid != user
            ):
                raise ValueError("MEMBER_OBSERVATION_SCOPE_INVALID")
            if previous is not None and not previous.user and row.user:
                raise ValueError("MEMBER_DELETED")
            self.records.write(
                directory, filename, row.model_dump(mode="json"), replace=previous is not None
            )
