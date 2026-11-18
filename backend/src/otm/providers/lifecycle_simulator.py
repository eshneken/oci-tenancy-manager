"""Deterministic local lifecycle implementation; no usable credentials or live OCI effects."""

from hashlib import sha256

from otm.operations.contracts import InspectionPolicy
from otm.providers.lifecycle import (
    LifecycleBlocked,
    LifecycleCompletion,
    MemberBinding,
    OnboardingUsers,
)
from otm.providers.required_user_contracts import ObservedRequiredUser
from otm.tenancies.contracts import MemberRemoval
from otm.tenancies.views import CompartmentOption, CreationRegion


# Synthetic IDs are deterministic across process restarts; no external OCI effect is claimed.
class SimulatedLifecycleFacade:
    # Resolve trusted scope from the same explicit local sandbox policy used by the worker.
    def __init__(
        self,
        policy: InspectionPolicy,
        *,
        recovery_console=None,
        recovery_console_loader=None,
        automation_keys=None,
        signing_keys=None,
        member_inventory=None,
    ):
        from otm.providers.configuration_simulator import SimulatedConfigurationFacade

        self.policy = policy
        self.automation_keys = automation_keys
        self.signing_keys = signing_keys
        self.recovery_console = recovery_console
        self.recovery_console_loader = recovery_console_loader
        self.configuration_facade = SimulatedConfigurationFacade(policy)
        self._member_access = {}
        from otm.providers.member_inventory_simulator import MemberInventory

        self.member_inventory = MemberInventory(member_inventory)
        if self.member_inventory.records is None:
            self._member_access = self.member_inventory.memory

    # Local choices simulate parent subscriptions; production must discover them through the
    # parent SDK.
    def creation_regions(self):
        return (
            CreationRegion(identifier="us-ashburn-1", name="US East (Ashburn)"),
            CreationRegion(identifier="us-phoenix-1", name="US West (Phoenix)"),
            CreationRegion(identifier="eu-frankfurt-1", name="Germany Central (Frankfurt)"),
        )

    # Discover root and two stable simulated existing compartments for the selected registered
    # child.
    def compartments(self, tenancy_ocid):
        if (
            not tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
            or tenancy_ocid == self.policy.parent_tenancy_ocid
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        suffix = sha256(tenancy_ocid.encode()).hexdigest()[:24]
        return (
            CompartmentOption(ocid=tenancy_ocid, name="Root compartment"),
            CompartmentOption(
                ocid="ocid1.compartment.oc1..otmsimprojects" + suffix, name="Projects"
            ),
            CompartmentOption(
                ocid="ocid1.compartment.oc1..otmsimshared" + suffix, name="Shared environments"
            ),
        )

    # Predictable nonusable account IDs let local tests exercise the exact-account handoff.
    def onboarding_handoff(self, intent):
        from otm.tenancies.onboarding_contracts import OnboardingHandoff

        suffix = intent.pending_tenancy_id.hex
        return OnboardingHandoff(
            tenancy_ocid=intent.target.tenancy_ocid,
            bootstrap_user_ocid="ocid1.user.oc1..otmsimbootstrap" + suffix,
            activation_user_ocid="ocid1.user.oc1..otmsimactivation" + suffix
            if intent.action == "create_tenancy"
            else None,
        )

    # Discovery checks exact synthetic identity and parent scope; confirmation is never evidence.
    def inspect_onboarding(self, intent, handoff):
        from otm.tenancies.onboarding_contracts import OnboardingDiscovery

        self.validate_scope(intent)
        if handoff != self.onboarding_handoff(intent):
            raise ValueError("BOOTSTRAP_UNVERIFIED")
        suffix = intent.pending_tenancy_id.hex
        return OnboardingDiscovery(
            tenancy_ocid=handoff.tenancy_ocid,
            name=intent.name or "sandbox-" + suffix[:12],
            home_region=(intent.home_region or "us-ashburn-1")
            if intent.action == "create_tenancy"
            else "us-ashburn-1",
            parent_tenancy_ocid=intent.parent_tenancy_ocid,
            organization_id=intent.organization_id,
            domain_ocid="ocid1.domain.oc1..otmsim" + suffix,
            bootstrap_user_ocid=handoff.bootstrap_user_ocid,
            bootstrap_scim_id="bootstrap-" + suffix,
            activation_user_ocid=handoff.activation_user_ocid,
            activation_scim_id="activation-" + suffix if handoff.activation_user_ocid else None,
        )

    # Existing human accounts are read independently; directory assignments never create inventory.
    def inspect_existing_access(self, tenancy_ocid, domain_ocid):
        from otm.providers.import_inventory_simulator import existing_inventory

        if not domain_ocid.startswith("ocid1.domain.oc1..otmsim"):
            raise ValueError("IMPORT_DOMAIN_UNVERIFIED")
        self._member_access.update(self.member_inventory.read(tenancy_ocid))
        initial = existing_inventory(
            tenancy_ocid, domain_ocid, self.compartments(tenancy_ocid), self._member_access
        )
        from otm.tenancies.import_contracts import ExistingIdentity, stored_import

        users = {user.user_ocid: user for user in initial.users}
        for (child, user), state in self._member_access.items():
            if child != tenancy_ocid:
                continue
            if not state["user"]:
                users.pop(user, None)
            elif not state["groups"] and user in users:
                users[user] = users[user].model_copy(update={"groups": (), "administrator": False})
            elif state.get("identity") is not None and state.get("domain_ocid") == domain_ocid:
                identity = stored_import(ExistingIdentity, state["identity"])
                users[user] = (
                    identity
                    if state["groups"]
                    else identity.model_copy(update={"groups": (), "administrator": False})
                )
        return initial.model_copy(
            update={"users": tuple(sorted(users.values(), key=lambda u: u.user_ocid))}
        )

    # Imported owner/member identities are already established; only OTM service access is
    # configured.
    def configure_import_access(self, intent, discovery, manifest):
        self.validate_scope(intent)
        if not manifest.members:
            raise ValueError("IMPORT_MANIFEST_REQUIRED")
        self.onboarding_step(intent, "configure_required", discovery)

    # Each bounded capability verifies the same target; a real adapter requires separate
    # qualification.
    def onboarding_step(self, intent, key, discovery):
        current_console = (
            self.recovery_console_loader()
            if self.recovery_console_loader
            else self.recovery_console
        )
        if intent.recovery_console_fingerprint is not None and (
            current_console is None
            or current_console.fingerprint != intent.recovery_console_fingerprint
            or self.recovery_console is None
            or self.recovery_console.fingerprint != intent.recovery_console_fingerprint
        ):
            raise ValueError("TARGET_CHANGED")
        expected = self.inspect_onboarding(intent, self.onboarding_handoff(intent))
        if discovery != expected.model_dump(mode="json") or key not in {
            "establish_automation",
            "verify_automation",
            "configure_required",
            "verify_required",
            "retire_temporary",
        }:
            raise ValueError("TARGET_CHANGED")

        if key == "configure_required" and intent.automation_key_inventory_contract is not None:
            if self.automation_keys is None:
                raise ValueError("AUTOMATION_KEY_CAPTURE_UNAVAILABLE")
            self.automation_keys.configure(
                intent.workspace_id,
                intent.pending_tenancy_id,
                intent.target.tenancy_ocid,
                ObservedRequiredUser(
                    domain_ocid=discovery["domain_ocid"],
                    scim_resource_id="automation-" + intent.pending_tenancy_id.hex,
                    provider_ocid="ocid1.user.oc1..otmsimautomation"
                    + intent.pending_tenancy_id.hex,
                    user_name="otm-automation",
                ),
                empty=intent.signing_key_rotation_contract is not None,
            )

    # Return explicit synthetic provider facts, stable across retries and distinct from bootstrap.
    def capture_onboarding_users(self, intent, discovery):
        self.onboarding_step(intent, "verify_required", discovery)
        suffix = intent.pending_tenancy_id.hex
        from otm.providers.recovery_console_simulator import configured_console_capture

        capture = (
            configured_console_capture(
                discovery["domain_ocid"], "recovery-" + suffix, suffix, self.recovery_console
            )
            if intent.recovery_console_fingerprint
            else None
        )
        from otm.providers.administrator_access_simulator import configured_administrator_capture

        return OnboardingUsers(
            workspace_id=intent.workspace_id,
            tenancy_ocid=intent.target.tenancy_ocid,
            parent_tenancy_ocid=intent.parent_tenancy_ocid,
            organization_id=intent.organization_id,
            domain_ocid=discovery["domain_ocid"],
            recovery_console=capture,
            automation_keys=self.automation_keys.read(
                intent.workspace_id,
                intent.pending_tenancy_id,
                intent.target.tenancy_ocid,
                ObservedRequiredUser(
                    domain_ocid=discovery["domain_ocid"],
                    scim_resource_id="automation-" + suffix,
                    provider_ocid="ocid1.user.oc1..otmsimautomation" + suffix,
                    user_name="otm-automation",
                ),
            )
            if intent.automation_key_inventory_contract is not None
            and self.automation_keys is not None
            else None,
            automation_administrator=configured_administrator_capture(
                discovery["domain_ocid"],
                "automation-" + suffix,
                suffix,
                ("automation-" + suffix, "recovery-" + suffix),
            ),
            recovery_administrator=configured_administrator_capture(
                discovery["domain_ocid"],
                "recovery-" + suffix,
                suffix,
                ("automation-" + suffix, "recovery-" + suffix),
            ),
            automation=ObservedRequiredUser(
                domain_ocid=discovery["domain_ocid"],
                scim_resource_id="automation-" + suffix,
                provider_ocid="ocid1.user.oc1..otmsimautomation" + suffix,
                user_name="otm-automation",
            ),
            recovery=ObservedRequiredUser(
                domain_ocid=discovery["domain_ocid"],
                scim_resource_id="recovery-" + suffix,
                provider_ocid="ocid1.user.oc1..otmsimrecovery" + suffix,
                user_name="otm-recovery",
            ),
        )

    # Simulated readback is exact-account scoped and never deletes a compartment or its resources.
    def remove_member_access(self, intent, association):
        if (
            not association.removes_identity
            or not association.user_ocid
            or not association.user_ocid.startswith("ocid1.user.oc1..otmsim")
            or association.tenancy_ocid == self.policy.parent_tenancy_ocid
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        key = (association.tenancy_ocid, association.user_ocid)
        self._member_access.update(self.member_inventory.read(association.tenancy_ocid))
        self._member_access.setdefault(key, {"groups": True, "user": True})
        self.remove_member_groups(association)
        self.delete_member_user(association)
        return self.read_member_access(association)

    # Remove only this user's group memberships, leaving shared groups and other users intact.
    def remove_member_groups(self, association):
        state = self._member_access[(association.tenancy_ocid, association.user_ocid)]
        state["groups"] = False
        self.member_inventory.write(association.tenancy_ocid, association.user_ocid, state)

    # Delete the exact personal user only after its group memberships have been retired.
    def delete_member_user(self, association):
        state = self._member_access[(association.tenancy_ocid, association.user_ocid)]
        if state["groups"]:
            raise LifecycleBlocked("TARGET_CHANGED")
        state["user"] = False
        self.member_inventory.write(association.tenancy_ocid, association.user_ocid, state)

    # Independent observation reads mutated fake provider state, rather than echoing desired flags.
    def read_member_access(self, association):
        state = self._member_access[(association.tenancy_ocid, association.user_ocid)]
        return MemberRemoval(
            association_id=association.id,
            tenancy_ocid=association.tenancy_ocid,
            user_ocid=association.user_ocid,
            group_memberships_removed=not state["groups"],
            user_deleted=not state["user"],
        )

    # Reject substituted workspace/organization/parent and protected targets before any capability.
    # Passing local simulation guards never qualifies a real provider or its access.
    def validate_scope(self, intent):
        if (
            intent.workspace_id,
            intent.policy_revision,
            intent.organization_id,
            intent.parent_tenancy_ocid,
        ) != (
            self.policy.workspace_id,
            self.policy.policy_revision,
            self.policy.organization_id,
            self.policy.parent_tenancy_ocid,
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        targets = [a.tenancy_ocid for a in intent.associations]
        if intent.target.tenancy_ocid:
            targets.append(intent.target.tenancy_ocid)
        if any(
            not t.startswith("ocid1.tenancy.oc1..otmsim") or t == intent.parent_tenancy_ocid
            for t in targets
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        if any(a.parent_tenancy_ocid != intent.parent_tenancy_ocid for a in intent.associations):
            raise LifecycleBlocked("TARGET_CHANGED")

    # Ordinary lifecycle actions retain the same exact-target deletion rules for adopted identities.
    def apply(self, intent):
        self.validate_scope(intent)
        bindings = []
        administrations = []
        for item in intent.associations:
            if item.action == "transfer":
                suffix = sha256(
                    (item.tenancy_ocid + str(item.recipient_person_id)).encode()
                ).hexdigest()[:32]
                self._member_access.update(self.member_inventory.read(item.tenancy_ocid))
                candidate = "ocid1.user.oc1..otmsim" + suffix
                if self._member_access.get((item.tenancy_ocid, candidate), {}).get("user") is False:
                    candidate = (
                        "ocid1.user.oc1..otmsim"
                        + sha256(
                            (item.tenancy_ocid + str(item.new_association_id)).encode()
                        ).hexdigest()[:32]
                    )
                user = item.recipient_user_ocid or candidate
                if user == item.user_ocid or not user.startswith("ocid1.user.oc1..otmsim"):
                    raise LifecycleBlocked("TARGET_CHANGED")
                if item.owner_administration_required:
                    administrations.append(self.promote_owner(item, user))
                bindings.append(
                    MemberBinding(
                        association_id=item.new_association_id,
                        tenancy_ocid=item.tenancy_ocid,
                        person_id=item.recipient_person_id,
                        user_ocid=user,
                        compartment_ocid=item.tenancy_ocid
                        if item.owner_administration_required
                        else item.recipient_compartment_ocid,
                        parent_compartment_ocid=None
                        if item.owner_administration_required
                        else item.recipient_parent_compartment_ocid,
                    )
                )
        if intent.pending_association_id is not None:
            tenant = intent.target.tenancy_ocid
            if tenant is None:
                raise LifecycleBlocked("TARGET_CHANGED")
            if intent.action == "join_shared" and (
                intent.existing_compartment_ocid or intent.parent_compartment_ocid
            ) not in {p.ocid for p in self.compartments(tenant)}:
                raise LifecycleBlocked("TARGET_CHANGED")
            suffix = sha256((tenant + str(intent.target.person_id)).encode()).hexdigest()[:32]
            self._member_access.update(self.member_inventory.read(tenant))
            if (
                self._member_access.get((tenant, "ocid1.user.oc1..otmsim" + suffix), {}).get("user")
                is False
            ):
                suffix = sha256((tenant + str(intent.pending_association_id)).encode()).hexdigest()[
                    :32
                ]
            bindings.append(
                MemberBinding(
                    association_id=intent.pending_association_id,
                    tenancy_ocid=tenant,
                    person_id=intent.target.person_id,
                    user_ocid="ocid1.user.oc1..otmsim" + suffix,
                    compartment_ocid=intent.existing_compartment_ocid
                    or ("ocid1.compartment.oc1..otmsim" + intent.pending_association_id.hex)
                    if intent.action == "join_shared"
                    else None,
                    parent_compartment_ocid=intent.parent_compartment_ocid,
                )
            )
        if intent.pending_association_id is not None:
            created = bindings[-1]
            domain = intent.member_domain_ocid or (
                "ocid1.domain.oc1..otmsim" + intent.pending_tenancy_id.hex
                if intent.pending_tenancy_id
                else None
            )
            if domain:
                self.create_member(
                    created.tenancy_ocid,
                    domain,
                    created.user_ocid,
                    created.compartment_ocid or created.tenancy_ocid,
                    administrator=intent.action != "join_shared",
                )
        from otm.tenancies.owner_access import validate

        validate(
            intent,
            LifecycleCompletion(
                bindings=tuple(bindings), owner_administrations=tuple(administrations)
            ),
        )
        # Establish and validate replacement identity before deleting any outgoing owner.
        by_association = {binding.association_id: binding for binding in bindings}
        for item in intent.associations:
            if item.action == "transfer":
                replacement = by_association[item.new_association_id]
                if replacement.user_ocid == item.user_ocid or not replacement.user_ocid.startswith(
                    "ocid1.user.oc1..otmsim"
                ):
                    raise LifecycleBlocked("TARGET_CHANGED")
        return LifecycleCompletion(
            owner_administrations=tuple(administrations),
            bindings=tuple(bindings),
            removals=tuple(
                self.remove_member_access(intent, item)
                for item in intent.associations
                if item.removes_identity
            ),
        )

    # Provision a new simulated identity in provider state; tombstones never authorize resurrection.
    def create_member(self, tenancy, domain, user, scope, *, administrator=False):
        from otm.tenancies.import_contracts import ExistingIdentity, ExistingScope
        from otm.tenancies.owner_access import promoted

        self._member_access.update(self.member_inventory.read(tenancy))
        current = self._member_access.get((tenancy, user))
        if current is not None:
            if not current["user"]:
                raise LifecycleBlocked("TARGET_CHANGED")
            return
        identity = ExistingIdentity(
            user_ocid=user,
            scim_id="member-" + sha256(user.encode()).hexdigest()[:24],
            user_name="Managed member",
            email="member-" + sha256(user.encode()).hexdigest()[:12] + "@example.test",
            administrator=False,
            scopes=(
                ExistingScope(
                    ocid=scope,
                    name="Root compartment" if scope == tenancy else "Member compartment",
                    kind="root" if scope == tenancy else "compartment",
                ),
            ),
            policy_hash=sha256(("member-grants-" + user).encode()).hexdigest(),
        )
        if administrator:
            identity = promoted(identity, tenancy, domain)
        state = {
            "user": True,
            "groups": True,
            "domain_ocid": domain,
            "identity": identity.model_dump(mode="json"),
        }
        self.member_inventory.write(tenancy, user, state)
        self._member_access[(tenancy, user)] = state

    # Apply additive administrator grants, then inspect provider state independently before
    # deletion.
    def promote_owner(self, item, user):
        from otm.tenancies.owner_access import profile, promoted

        domain = item.recipient_domain_ocid
        if item.recipient_user_ocid is None:
            self.create_member(item.tenancy_ocid, domain, user, item.tenancy_ocid)
        current = self.inspect_member(item.tenancy_ocid, domain, user)
        if current is None:
            raise LifecycleBlocked("TARGET_CHANGED")
        grant = profile(item.tenancy_ocid, domain)
        updated = promoted(current, item.tenancy_ocid, domain)
        state = dict(
            self._member_access.get((item.tenancy_ocid, user), {}),
            user=True,
            groups=True,
            domain_ocid=domain,
            identity=updated.model_dump(mode="json"),
            root_policy_id=grant["policy"],
            policy_group_id=grant["group"],
            policy_scope_ocid=item.tenancy_ocid,
            manage_all_resources=True,
            domain_administrator=True,
        )
        self.member_inventory.write(item.tenancy_ocid, user, state)
        self._member_access[(item.tenancy_ocid, user)] = state
        proof = self.inspect_owner(item, user)
        if proof.identity.scim_id != current.scim_id:
            raise LifecycleBlocked("TARGET_CHANGED")
        return proof

    # Return the observed group/policy/role linkage, not booleans copied from the requested grants.
    def inspect_owner(self, item, user):
        from otm.tenancies.owner_access import profile
        from otm.tenancies.owner_access_contracts import OwnerAdministration

        inventory = self.inspect_existing_access(item.tenancy_ocid, item.recipient_domain_ocid)
        identity = next(u for u in inventory.users if u.user_ocid == user)
        state = self._member_access[(item.tenancy_ocid, user)]
        grant = profile(item.tenancy_ocid, item.recipient_domain_ocid)
        return OwnerAdministration(
            association_id=item.new_association_id,
            tenancy_ocid=item.tenancy_ocid,
            domain_ocid=item.recipient_domain_ocid,
            identity=identity,
            administrator_group_id=grant["group"],
            administrator_role_id=grant["role"],
            root_policy_id=state["root_policy_id"],
            policy_group_id=state["policy_group_id"],
            policy_scope_ocid=state["policy_scope_ocid"],
            manage_all_resources=state["manage_all_resources"],
            domain_administrator=state["domain_administrator"],
            authorized=True,
            supported=True,
            complete=inventory.complete,
        )

    # Resolve exact observed IDs; legacy deterministic fixture IDs have a stable provider-side
    # default.
    def inspect_member(self, tenancy, domain, user):
        import re

        from otm.tenancies.import_contracts import ExistingIdentity, ExistingScope

        inventory = self.inspect_existing_access(tenancy, domain)
        if (
            not inventory.complete
            or inventory.tenancy_ocid != tenancy
            or inventory.domain_ocid != domain
        ):
            raise ValueError("MEMBER_OBSERVATION_UNVERIFIED")
        match = next(
            (candidate for candidate in inventory.users if candidate.user_ocid == user), None
        )
        if match is not None:
            return match
        if (tenancy, user) in self._member_access or not re.fullmatch(
            r"ocid1\.user\.oc1\.\.otmsim[0-9a-f]{32}", user
        ):
            return None
        return ExistingIdentity(
            user_ocid=user,
            scim_id="member-" + sha256(user.encode()).hexdigest()[:24],
            user_name="Managed member",
            email="member-" + sha256(user.encode()).hexdigest()[:12] + "@example.test",
            administrator=False,
            scopes=(
                ExistingScope(
                    ocid=self.compartments(tenancy)[1].ocid,
                    name=self.compartments(tenancy)[1].name,
                    kind="compartment",
                ),
            ),
            policy_hash=sha256(("member-grants-" + user).encode()).hexdigest(),
        )
