"""Independent synthetic existing-account inventory; no IAM calls or usable credentials."""

from hashlib import sha256

from otm.tenancies.import_contracts import (
    ExistingAccessInventory,
    ExistingIdentity,
    ExistingScope,
)


# Stable preexisting identities are independent of submitted directory matches or adoption choices.
def existing_inventory(tenancy_ocid, domain_ocid, compartments, member_access):
    suffix = sha256((tenancy_ocid + domain_ocid).encode()).hexdigest()[:24]
    scopes = tuple(
        ExistingScope(
            ocid=c.ocid,
            name=c.name,
            kind="root" if c.ocid == tenancy_ocid else "compartment",
        )
        for c in compartments
    )
    users = []
    for index, label in enumerate(("Existing owner", "Existing administrator", "Existing analyst")):
        user = "ocid1.user.oc1..otmsimexisting" + str(index) + suffix
        if not member_access.get((tenancy_ocid, user), {}).get("user", True):
            continue
        users.append(
            ExistingIdentity(
                user_ocid=user,
                scim_id="existing-" + str(index) + suffix,
                user_name=label,
                email="existing" + str(index) + "@example.test",
                administrator=index < 2,
                groups=("group-admin-" + suffix,) if index < 2 else ("group-project-" + suffix,),
                roles=("role-domain-admin-" + suffix,) if index < 2 else (),
                scopes=scopes[:1] if index < 2 else scopes[1:],
                policy_hash=sha256(("existing-grants-" + str(index) + suffix).encode()).hexdigest(),
            )
        )
    return ExistingAccessInventory(
        tenancy_ocid=tenancy_ocid, domain_ocid=domain_ocid, complete=True, users=tuple(users)
    )
