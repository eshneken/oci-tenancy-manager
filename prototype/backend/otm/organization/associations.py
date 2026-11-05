"""Local simulated tenancy registry with atomic, association-aware offboarding decisions."""

import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select, update

from otm.organization.contracts import ReviewDecision
from otm.organization.review_rules import issue_basis
from otm.organization.store import PublicationConflict


# Freeze registry evidence as JSON without exposing connection details or credentials.
def serializable(value):
    return json.loads(
        json.dumps(value, default=lambda v: sorted(v) if isinstance(v, set) else str(v))
    )


# Manage prototype associations; every operation is simulated and calls no OCI service.
class TenancyRegistry:
    # Scope all registry reads and writes to the same organization workspace/run.
    def __init__(self, store, workspace):
        self.store, self.workspace = store, workspace

    # Read persisted rows or reconstruct conservative legacy simulations without writing.
    def _state(self, connection, config):
        state = {}
        for key in ("tenancy", "association"):
            table = self.store.tables[key]
            state[key] = [
                dict(r)
                for r in connection.execute(
                    select(table).where(table.c.workspace_id == self.workspace)
                ).mappings()
            ]
        state["hidden"] = {str(i) for i in config.managed_exclusions}
        state["warnings"] = []
        state["outside"] = {str(i) for i in config.outside_person_ids}
        state["pending"] = {str(i) for i in config.pending_onboarding_person_ids}
        if config.registry_initialized:
            self._restore_feed_returns(connection, config, state)
            return state
        # IDs must be deterministic across read-only previews and the eventual bootstrap.
        for index, decision in enumerate(config.review_decisions):
            if not decision.person_id or decision.simulation != "succeeded":
                continue
            person = str(decision.person_id)
            token = str(uuid5(NAMESPACE_URL, f"otm:{self.workspace}:{index}:{person}"))
            if decision.operation in {"create_tenancy", "import_tenancy", "shared_membership"}:
                shared = decision.operation == "shared_membership"
                state["tenancy"].append(
                    {
                        "id": token,
                        "workspace_id": self.workspace,
                        "name": f"Legacy {'shared' if shared else 'individual'} {token[:8]}",
                        "kind": "shared" if shared else "individual",
                        "status": "active",
                        "legacy": True,
                        "created_at": decision.recorded_at,
                        "updated_at": decision.recorded_at,
                    }
                )
                state["association"].append(
                    {
                        "id": str(uuid5(NAMESPACE_URL, token + ":association")),
                        "workspace_id": self.workspace,
                        "tenancy_id": token,
                        "person_id": person,
                        "role": "member" if shared else "owner",
                        "status": "active",
                        "created_at": decision.recorded_at,
                        "updated_at": decision.recorded_at,
                    }
                )
                if shared:
                    state["warnings"].append(
                        "A legacy shared membership has no recorded owner. "
                        "Assign an owner before adding members."
                    )
            elif decision.operation == "keep_tenancy":
                state["outside"].add(person)
            elif decision.operation == "delete_tenancy":
                owned = [
                    a
                    for a in state["association"]
                    if a["person_id"] == person and a["status"] == "active" and a["role"] == "owner"
                ]
                if len(owned) == 1:
                    owned[0]["status"] = "removed"
                    next(t for t in state["tenancy"] if t["id"] == owned[0]["tenancy_id"])[
                        "status"
                    ] = "deleted"
                    if not self._links(state, person):
                        state["hidden"].add(person)
                else:
                    state["warnings"].append(
                        "An earlier simulated deletion did not identify a unique tenancy. "
                        "Review preserved associations before offboarding."
                    )
        for decision in config.review_decisions:
            if decision.operation == "no_tenancy_required" and decision.person_id:
                person = str(decision.person_id)
                if not self._links(state, person):
                    state["hidden"].add(person)
        self._restore_feed_returns(connection, config, state)
        return state

    # Project fresh onboarding after qualified absence and return, without mutating reads.
    #
    # An explicit no-tenancy decision remains durable. Completed offboarding is different:
    # an applied full feed with positive employee evidence after a qualified absence opens
    # onboarding again. Historical absence timestamps survive review closure, so repeated
    # present feeds cannot erase the pending return or require guessing from an old name.
    def _restore_feed_returns(self, connection, config, state):
        if not state["hidden"]:
            return
        current = self.store._workspace(connection, self.workspace)
        if not current["applied_version_id"]:
            return
        head = self.store._revision(connection, current["applied_version_id"])
        profiles = {str(p.id): p for p in head.people if p.profile == "employee"}
        endings = {}
        for decision in config.review_decisions:
            key = str(decision.person_id)
            if key in state["hidden"] and decision.operation in {
                "offboard_person",
                "delete_tenancy",
                "remove_member",
                "transfer_owner",
                "no_tenancy_required",
            }:
                if key not in endings or decision.recorded_at >= endings[key].recorded_at:
                    endings[key] = decision
        eligible = {
            key: d
            for key, d in endings.items()
            if key in profiles
            and d.operation != "no_tenancy_required"
            and not self._links(state, key)
        }
        if not eligible:
            return
        versions, members = self.store.tables["version"], self.store.tables["member"]
        evidence = connection.execute(
            select(
                members.c.person_id,
                versions.c.data,
                members.c.evidence,
                members.c.data["absence_review_since"].as_string(),
            )
            .join(versions, members.c.version_id == versions.c.id)
            .where(
                versions.c.workspace_id == self.workspace,
                versions.c.kind == "applied",
                members.c.person_id.in_(eligible),
            )
        ).all()
        absent = set()
        # A settled absence keeps its qualified episode timestamp even when an admin
        # offboards days later and the original source snapshot has since become stale.
        for identity, decision in eligible.items():
            if decision.kind == "PERSON_ABSENCE_REVIEW" and decision.basis not in {None, "legacy"}:
                try:
                    datetime.fromisoformat(decision.basis)
                except ValueError:
                    continue
                absent.add(identity)
        # Replay only qualified evidence after the last terminal decision. A return is
        # durable even if a subsequent snapshot omits the employee again before onboarding.
        for identity, version_data, presence, since in sorted(
            evidence, key=lambda row: datetime.fromisoformat(row[1]["published_at"])
        ):
            at = datetime.fromisoformat(version_data["published_at"])
            if not (
                version_data["absence_eligible"]
                and endings[identity].recorded_at <= at <= head.published_at
            ):
                continue
            if since:
                absent.add(identity)
            if identity in absent and presence == "feed_row" and at > endings[identity].recorded_at:
                state["hidden"].discard(identity)
                state["outside"].discard(identity)
                state["pending"].add(identity)

    # Select active associations only, optionally restricted by person or tenancy.
    @staticmethod
    def _links(state, person=None, tenancy=None):
        return [
            a
            for a in state["association"]
            if a["status"] == "active"
            and (person is None or a["person_id"] == person)
            and (tenancy is None or a["tenancy_id"] == tenancy)
        ]

    # Retain source/reporting identities independently from managed-directory inclusion.
    def _people(self, connection, head, config, state):
        result = (
            {
                str(p.id): {
                    "id": str(p.id),
                    "name": p.full_name or p.email,
                    "email": p.email,
                    "profile": p.profile,
                    "is_manager": p.known_manager,
                }
                for p in head.people
            }
            if head
            else {}
        )
        source = {}
        if head:
            data = connection.execute(
                select(self.store.tables["feed"].c.data).where(
                    self.store.tables["feed"].c.id == str(head.snapshot_id)
                )
            ).scalar_one()
            source = {r["email"]: r for r in data["records"]}
        needed = {a["person_id"] for a in state["association"]} | state["hidden"]
        table = self.store.tables["person"]
        # Legacy excluded profiles may still exist in source and immutable identity history.
        for row in connection.execute(
            select(table).where(table.c.id.in_(needed) | table.c.email.in_(config.excluded_emails))
        ).mappings():
            if row["id"] not in result:
                address = row["email"]
                result[row["id"]] = {
                    "id": row["id"],
                    "name": source.get(address, {}).get("full_name", address),
                    "email": address,
                    "profile": "employee",
                }
        for person in result.values():
            person["source_present"] = person["email"] in source
            person["managed"] = (
                person["id"] not in state["hidden"]
                and person["email"] not in config.excluded_emails
            )
            person["eligible_transfer"] = bool(
                person["managed"]
                and person["source_present"]
                and person["profile"] == "employee"
                and person["id"] not in state["outside"]
            )
        return result

    # Return the registry projection and explicit re-onboarding candidates without mutation.
    def read(self):
        config, head = self.store.configuration(self.workspace), self.store.head(self.workspace)
        with self.store.engine.connect() as connection:
            state = self._state(connection, config)
            people = self._people(connection, head, config, state)
        tenancies = []
        for tenancy in state["tenancy"]:
            if tenancy["status"] != "active":
                continue
            links = self._links(state, tenancy=tenancy["id"])
            owner = next((a for a in links if a["role"] == "owner"), None)
            owner_person = people.get(owner["person_id"], {}) if owner else {}
            tenancies.append(
                {
                    **serializable(tenancy),
                    "owner_person_id": owner["person_id"] if owner else None,
                    "owner_name": owner_person.get("name"),
                    "owner_email": owner_person.get("email"),
                    "member_count": sum(a["role"] == "member" for a in links),
                    "associations": serializable(links),
                }
            )
        by_id = {t["id"]: t for t in tenancies}
        for person in people.values():
            associations = []
            for association in self._links(state, person["id"]):
                tenancy = by_id[association["tenancy_id"]]
                actions, blocks = ["keep"], {}
                if association["role"] == "member":
                    actions.insert(0, "remove")
                else:
                    actions.insert(0, "transfer")
                    if tenancy["kind"] == "individual" and not tenancy["member_count"]:
                        actions.insert(0, "delete")
                    else:
                        blocks["delete"] = (
                            "Transfer shared tenancy ownership first."
                            if tenancy["kind"] == "shared"
                            else "Remove other members before deleting this tenancy."
                        )
                associations.append(
                    {
                        **serializable(association),
                        "tenancy_name": tenancy["name"],
                        "kind": tenancy["kind"],
                        "member_count": tenancy["member_count"],
                        "legacy": tenancy["legacy"],
                        "allowed_actions": actions,
                        "block_reasons": blocks,
                    }
                )
            person["associations"] = associations
            person["association_count"] = len(associations)
            person["onboarding_required"] = person["id"] in state["pending"]
            person["status"] = (
                "Not managed"
                if not person["managed"]
                else "Outside organization · association retained"
                if person["id"] in state["outside"]
                or (associations and not person["source_present"])
                else "Onboarding"
                if person["onboarding_required"]
                else "Managed"
            )
        profiles = [p for p in people.values() if p["profile"] == "employee"]
        return {
            "context": self.store.workspace_context(self.workspace),
            "people": profiles,
            "tenancies": tenancies,
            "unmanaged_people": [p for p in profiles if not p["managed"]],
            "legacy_bootstrap_pending": not config.registry_initialized,
            "warnings": state["warnings"],
        }

    # Persist soft state changes before inserts so partial unique indexes remain satisfied.
    def _save(self, connection, original, state):
        for key in ("tenancy", "association"):
            table = self.store.tables[key]
            existing = {r["id"]: r for r in original[key]}
            # On first bootstrap original physical rows are empty, not the legacy projection.
            persisted = set(
                connection.execute(
                    select(table.c.id).where(table.c.workspace_id == self.workspace)
                ).scalars()
            )
            for row in state[key]:
                if row["id"] in persisted and row["status"] in {"removed", "deleted"}:
                    connection.execute(update(table).where(table.c.id == row["id"]).values(**row))
            for row in state[key]:
                if row["id"] not in persisted:
                    connection.execute(table.insert().values(**row))
                elif row != existing.get(row["id"]) and row["status"] not in {"removed", "deleted"}:
                    connection.execute(update(table).where(table.c.id == row["id"]).values(**row))

    # Apply one validated registry command, audit and organization publication atomically.
    def operate(self, command):
        store, now = self.store, datetime.now(UTC)
        supplied_reason = command.get("reason")
        reason = (
            supplied_reason.strip()
            if supplied_reason is not None
            else "Administrator selected " + command["operation"].replace("_", " ") + "."
        )
        if len(reason) < 3:
            raise ValueError("A meaningful administrator reason is required.")
        expected, operation = command["context"], command["operation"]
        person_id = str(command["person_id"])
        with store.engine.begin() as connection:
            workspace = store._workspace(connection, self.workspace, lock=True)
            for field in ("applied_version_id", "proposed_version_id", "configuration_id"):
                if str(workspace[field]) != str(expected[field]):
                    raise PublicationConflict(
                        "Registry context changed. Refresh and confirm again."
                    )
            if (
                expected["workspace_id"] != self.workspace
                or workspace["applied_version_id"] != workspace["proposed_version_id"]
                and store.workspace_context(self.workspace)["proposal_status"] != "already_applied"
            ):
                raise PublicationConflict(
                    "Apply the pending organization proposal before changing associations."
                )
            config = store.configuration(self.workspace)
            head = store.head(self.workspace)
            if not head:
                raise ValueError("Load an organization snapshot first.")
            state = self._state(connection, config)
            original = serializable(state)
            people = self._people(connection, head, config, state)
            person = people.get(person_id)
            if not person or person["profile"] != "employee":
                raise ValueError("Choose an employee in this workspace.")
            pending = state["pending"]
            hidden = state["hidden"]
            outside = state["outside"]
            updates = {"registry_initialized": True}
            decisions = list(config.review_decisions)

            # Require a known active tenancy in this workspace, never an arbitrary OCI ID.
            def tenancy_for(identifier):
                found = next(
                    (
                        t
                        for t in state["tenancy"]
                        if t["id"] == str(identifier) and t["status"] == "active"
                    ),
                    None,
                )
                if not found:
                    raise ValueError("Choose an active registered tenancy in this workspace.")
                return found

            # Create one active association without silently duplicating existing access.
            def add_link(tenancy, target, role):
                if self._links(state, target, tenancy):
                    raise ValueError("This employee already has an association with that tenancy.")
                state["association"].append(
                    {
                        "id": str(uuid4()),
                        "workspace_id": self.workspace,
                        "tenancy_id": tenancy,
                        "person_id": target,
                        "role": role,
                        "status": "active",
                        "created_at": now,
                        "updated_at": now,
                    }
                )

            # Transfer to a current managed employee and retire the former association.
            def transfer(link, recipient):
                recipient = str(recipient)
                if recipient == link["person_id"] or not people.get(recipient, {}).get(
                    "eligible_transfer"
                ):
                    raise ValueError(
                        "Choose a different, currently present managed employee as owner."
                    )
                for member in self._links(state, recipient, link["tenancy_id"]):
                    member.update(status="removed", updated_at=now)
                link.update(status="removed", updated_at=now)
                add_link(link["tenancy_id"], recipient, "owner")
                pending.discard(recipient)
                decisions.append(
                    ReviewDecision(
                        kind="TENANCY_SETUP_REVIEW",
                        target=people[recipient]["email"],
                        disposition="resolved",
                        recorded_at=now,
                        actor="local:admin",
                        reason=reason,
                        person_id=recipient,
                        operation="transfer_owner",
                    )
                )

            # Enforce owner/member guards for direct actions and offboarding.
            def apply_action(link, action, recipient=None):
                tenancy = tenancy_for(link["tenancy_id"])
                if action == "keep":
                    return
                if action == "transfer" and link["role"] == "owner":
                    transfer(link, recipient)
                elif action == "remove" and link["role"] == "member":
                    link.update(status="removed", updated_at=now)
                elif action == "delete" and link["role"] == "owner":
                    if tenancy["kind"] == "shared":
                        raise ValueError(
                            "Transfer shared tenancy ownership before offboarding its owner."
                        )
                    if any(
                        a["person_id"] != person_id
                        for a in self._links(state, tenancy=tenancy["id"])
                    ):
                        raise ValueError(
                            "Remove other members before deleting an individually owned tenancy."
                        )
                    link.update(status="removed", updated_at=now)
                    tenancy.update(status="deleted", updated_at=now)
                else:
                    raise ValueError("This action is not allowed for the selected association.")

            if operation == "reonboard":
                if (
                    person["managed"]
                    or not person["source_present"]
                    or self._links(state, person_id)
                ):
                    raise ValueError(
                        "Re-onboarding requires a present, unmanaged employee with no associations."
                    )
                hidden.discard(person_id)
                outside.discard(person_id)
                pending.add(person_id)
                updates["excluded_emails"] = tuple(
                    e for e in config.excluded_emails if e != person["email"]
                )
                decisions = [
                    d
                    for d in decisions
                    if not (
                        d.kind == "TENANCY_SETUP_REVIEW"
                        and (d.person_id == UUID(person_id) or d.target == person["email"])
                    )
                ]
            else:
                if not person["managed"]:
                    raise ValueError(
                        "Re-onboard this employee before adding or changing associations."
                    )
                if operation in {"create_tenancy", "import_tenancy", "join_shared"} and (
                    not person["source_present"] or person_id in outside
                ):
                    raise ValueError(
                        "Verify the employee is present in the organization feed before onboarding."
                    )
                if operation == "return_to_org":
                    if not person["source_present"] or person_id not in outside:
                        raise ValueError("Choose a returned employee with retained associations.")
                    outside.discard(person_id)
                elif operation in {"create_tenancy", "import_tenancy"}:
                    kind = command.get("kind") or "individual"
                    name = (command.get("name") or f"Simulated tenancy {str(uuid4())[:8]}").strip()
                    if (
                        not name
                        or len(name) > 200
                        or any(
                            t["name"].casefold() == name.casefold() and t["status"] == "active"
                            for t in state["tenancy"]
                        )
                    ):
                        raise ValueError(
                            "Use a distinct tenancy name between 1 and 200 characters."
                        )
                    tenancy = {
                        "id": str(uuid4()),
                        "workspace_id": self.workspace,
                        "name": name,
                        "kind": kind,
                        "status": "active",
                        "legacy": False,
                        "created_at": now,
                        "updated_at": now,
                    }
                    state["tenancy"].append(tenancy)
                    add_link(tenancy["id"], person_id, "owner")
                elif operation == "join_shared":
                    tenancy = tenancy_for(command.get("tenancy_id"))
                    if tenancy["kind"] != "shared" or not any(
                        a["role"] == "owner" for a in self._links(state, tenancy=tenancy["id"])
                    ):
                        raise ValueError("Choose a shared tenancy with a recorded owner.")
                    add_link(tenancy["id"], person_id, "member")
                elif operation == "assign_owner":
                    tenancy = tenancy_for(command.get("tenancy_id"))
                    if tenancy["kind"] != "shared" or any(
                        a["role"] == "owner" for a in self._links(state, tenancy=tenancy["id"])
                    ):
                        raise ValueError(
                            "Assign owner is only available for a shared tenancy without an owner."
                        )
                    if not person["eligible_transfer"]:
                        raise ValueError("Choose a present managed employee as owner.")
                    for link in self._links(state, person_id, tenancy["id"]):
                        link.update(status="removed", updated_at=now)
                    add_link(tenancy["id"], person_id, "owner")
                elif operation == "update_tenancy":
                    tenancy = tenancy_for(command.get("tenancy_id"))
                    if not any(
                        a["role"] == "owner" for a in self._links(state, person_id, tenancy["id"])
                    ):
                        raise ValueError("Choose the registered owner to edit this tenancy.")
                    name = (command.get("name") or tenancy["name"]).strip()
                    kind = command.get("kind") or tenancy["kind"]
                    if (
                        not name
                        or len(name) > 200
                        or any(
                            t["id"] != tenancy["id"]
                            and t["status"] == "active"
                            and t["name"].casefold() == name.casefold()
                            for t in state["tenancy"]
                        )
                    ):
                        raise ValueError(
                            "Use a distinct tenancy name between 1 and 200 characters."
                        )
                    if kind == "individual" and any(
                        a["role"] == "member" for a in self._links(state, tenancy=tenancy["id"])
                    ):
                        raise ValueError(
                            "Remove shared members before changing the tenancy to individual."
                        )
                    tenancy.update(name=name, kind=kind, updated_at=now)
                elif operation in {
                    "offboard_person",
                    "delete_tenancy",
                    "remove_member",
                    "transfer_owner",
                }:
                    links = self._links(state, person_id)
                    if operation == "offboard_person":
                        plan = command.get("plan") or []
                        if {p["association_id"] for p in plan} != {a["id"] for a in links} or len(
                            plan
                        ) != len(links):
                            raise ValueError(
                                "Choose exactly one action for every current association."
                            )
                        if not links and not command.get("confirm_no_associations"):
                            raise ValueError(
                                "Confirm that no tenancy associations remain before offboarding."
                            )
                        for item in plan:
                            apply_action(
                                next(a for a in links if a["id"] == item["association_id"]),
                                item["action"],
                                item.get("recipient_person_id"),
                            )
                    else:
                        tenancy = tenancy_for(command.get("tenancy_id"))
                        link = next((a for a in links if a["tenancy_id"] == tenancy["id"]), None)
                        if not link:
                            raise ValueError(
                                "This employee has no active association with that tenancy."
                            )
                        apply_action(
                            link,
                            {
                                "delete_tenancy": "delete",
                                "remove_member": "remove",
                                "transfer_owner": "transfer",
                            }[operation],
                            command.get("owner_person_id"),
                        )
                    if not self._links(state, person_id):
                        hidden.add(person_id)
                        outside.discard(person_id)
                    elif operation == "offboard_person" or not person["source_present"]:
                        outside.add(person_id)
                elif operation == "no_tenancy_required":
                    if self._links(state, person_id):
                        raise ValueError(
                            "Resolve existing associations before marking no tenancy required."
                        )
                    hidden.add(person_id)
                else:
                    raise ValueError("Unknown registry operation.")
                if operation != "update_tenancy":
                    pending.discard(person_id)
                    for kind in ("TENANCY_SETUP_REVIEW", "PERSON_ABSENCE_REVIEW"):
                        subject = next((p for p in head.people if str(p.id) == person_id), None)
                        decisions.append(
                            ReviewDecision(
                                kind=kind,
                                target=person["email"],
                                disposition="resolved",
                                person_id=person_id,
                                operation=operation,
                                recorded_at=now,
                                actor="local:admin",
                                reason=reason,
                                basis=issue_basis(kind, person["email"], (subject,))
                                if kind == "PERSON_ABSENCE_REVIEW" and subject
                                else None,
                            )
                        )
            # Registry writes, directory eligibility, review closure and audit are one commit.
            updates.update(
                id=uuid4(),
                managed_exclusions=tuple(UUID(i) for i in hidden),
                pending_onboarding_person_ids=tuple(UUID(i) for i in pending),
                review_decisions=tuple(decisions),
                outside_person_ids=tuple(UUID(i) for i in outside),
            )
            self._save(connection, original, state)
            result = store.update_configuration(
                config.model_copy(update=updates),
                expected_version_id=UUID(expected["applied_version_id"]),
                expected_proposed_id=UUID(expected["proposed_version_id"]),
                expected_configuration_id=UUID(expected["configuration_id"]),
                actor="local:admin",
                reason=reason,
                observed_at=now,
                connection=connection,
            )
            simulated = operation not in {"reonboard", "no_tenancy_required", "return_to_org"}
            store._audit(
                connection,
                self.workspace,
                "tenancy_registry_changed",
                now,
                {
                    "operation": operation,
                    "person_id": person_id,
                    "email": person["email"],
                    "name": person["name"],
                    "reason": reason,
                    "simulated": simulated,
                    "oci_performed": False,
                    "before": original,
                    "after": serializable(state),
                    "person_removed": person_id in hidden,
                    "remaining_associations": len(self._links(state, person_id)),
                },
                actor="local:admin",
            )
            return {
                "resolved": True,
                "operation": operation,
                "status": "succeeded",
                "simulated": simulated,
                "oci_performed": False,
                "person_removed": person_id in hidden,
                "remaining_associations": len(self._links(state, person_id)),
                "outcome": result.model_dump(mode="json"),
            }
