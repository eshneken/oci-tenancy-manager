"""Resumable replacement with durable checkpoints around provider calls and no secret data."""

from typing import Literal

from pydantic import model_validator

from otm.contracts import Contract
from otm.providers.automation_keys import AutomationKeyFacts
from otm.providers.signing_key_rotation import (
    ManagedSigningKey,
    SigningKeyMutation,
    SigningKeyReplacement,
    SigningKeyVersion,
    inventory_matches,
    qualified_signer,
    retired_inventory,
)


# One operation retains the old retirement obligation even after its current pointer changes.
class SigningRotationState(Contract):
    old: ManagedSigningKey
    phase: Literal["stage", "upload", "verify", "activate", "retire", "complete"] = "stage"
    candidate: SigningKeyVersion | None = None
    uploaded: ManagedSigningKey | None = None
    upload_dispatched: bool = False
    retire_dispatched: bool = False

    # Persisted phase data cannot invent a different candidate or lose the managed old identity.
    @model_validator(mode="after")
    def coherent(self):
        if (self.phase != "stage" and self.candidate is None) or (
            self.phase in {"verify", "activate", "retire", "complete"} and self.uploaded is None
        ):
            raise ValueError("SIGNING_ROTATION_STATE_INVALID")
        if self.uploaded is not None and self.uploaded.version != self.candidate:
            raise ValueError("SIGNING_ROTATION_STATE_INVALID")
        return self


# Fixed diagnostics carry no provider exceptions, secret references or private material.
class SigningRotationBlocked(ValueError):
    # Callers persist this allowlisted state with the unchanged owning operation and reservation.
    def __init__(self, code):
        super().__init__(code)
        self.code = code


# The durable host supplies checkpoint/CAS callbacks; this engine never opens a DB transaction.
class SigningKeyRotationEngine:
    # Explicit custody/provider composition forbids automatic old-key or recovery-user fallback.
    def __init__(self, custody, provider, clock):
        self.custody, self.provider, self.clock = custody, provider, clock

    # Checkpoint callback must commit before returning; false means dispatch authority was lost.
    def save(self, state, checkpoint):
        state = SigningRotationState.model_validate(state)
        if not checkpoint(state):
            raise SigningRotationBlocked("SIGNING_KEY_CONTEXT_CHANGED")
        return state

    # Revalidate exact candidate scope after every restart, not merely after its initial creation.
    def replacement(self, state, context):
        if state.candidate is None:
            raise SigningRotationBlocked("SIGNING_KEY_CANDIDATE_UNAVAILABLE")
        return SigningKeyReplacement(context=context, old=state.old, candidate=state.candidate)

    # Complete independent subject coverage is required before interpreting any inventory row.
    def inventory(self, material, context):
        facts = AutomationKeyFacts.model_validate(self.provider.inventory(material, context))
        if not inventory_matches(facts, material.version.target):
            raise SigningRotationBlocked("SIGNING_KEY_INVENTORY_UNAVAILABLE")
        return facts

    # Probe the exact private version only; public listing cannot establish signer readiness.
    def probe(self, version, context):
        material = self.custody.material(version)
        if material.version != version:
            raise SigningRotationBlocked("SIGNING_KEY_CUSTODY_CHANGED")
        started = self.clock()
        observed = self.provider.probe(material, context)
        if not qualified_signer(observed, version, context, started, self.clock()):
            raise SigningRotationBlocked("SIGNING_KEY_PROBE_FAILED")
        return material

    # Finish only when exact old absence and continuing candidate capabilities independently agree.
    def retirement(self, state, context, checkpoint):
        replacement = self.replacement(state, context)
        candidate = self.probe(state.candidate, context)
        facts = self.inventory(candidate, context)
        if retired_inventory(facts, replacement, self.clock()):
            self.probe(state.candidate, context)
            return self.save(state.model_copy(update={"phase": "complete"}), checkpoint)
        old = next(
            (key for key in facts.keys if key.provider_key_id == state.old.provider_key_id), None
        )
        if old is None or old.fingerprint != state.old.version.fingerprint:
            raise SigningRotationBlocked("SIGNING_KEY_RETIREMENT_UNVERIFIED")
        # A crash after this commit leaves exact-key reconciliation, never a new target.
        state = self.save(state.model_copy(update={"retire_dispatched": True}), checkpoint)
        self.provider.retire(state.old, candidate, context)
        facts = self.inventory(candidate, context)
        if not retired_inventory(facts, replacement, self.clock()):
            raise SigningRotationBlocked("SIGNING_KEY_RETIREMENT_UNVERIFIED")
        self.probe(state.candidate, context)
        return self.save(state.model_copy(update={"phase": "complete"}), checkpoint)

    # One state transition is replayable; the host decides bounded scheduling and human resumption.
    def step(self, state, context, checkpoint, activate):
        state = SigningRotationState.model_validate(state)
        if context.workspace_id != state.old.version.target.workspace_id:
            raise SigningRotationBlocked("SIGNING_KEY_CONTEXT_CHANGED")
        if state.phase == "complete":
            return state
        if state.phase == "stage":
            candidate = self.custody.stage(state.old, context)
            SigningKeyReplacement(context=context, old=state.old, candidate=candidate)
            if candidate.material_created_at > self.clock():
                raise SigningRotationBlocked("SIGNING_KEY_CANDIDATE_UNAVAILABLE")
            return self.save(
                state.model_copy(update={"phase": "upload", "candidate": candidate}), checkpoint
            )
        self.replacement(state, context)
        if state.phase == "upload":
            return self.upload(state, context, checkpoint)
        if state.phase == "verify":
            self.probe(state.candidate, context)
            return self.save(state.model_copy(update={"phase": "activate"}), checkpoint)
        if state.phase == "activate":
            self.probe(state.candidate, context)
            next_state = state.model_copy(update={"phase": "retire"})
            # The host atomically publishes the new head and retiring phase while retaining old due.
            if not activate(next_state):
                raise SigningRotationBlocked("SIGNING_KEY_CONTEXT_CHANGED")
            return next_state
        return self.retirement(state, context, checkpoint)

    # Reconcile the persisted fingerprint first; an uncertain dispatch never creates another pair.
    def upload(self, state, context, checkpoint):
        old = self.custody.material(state.old.version)
        if old.version != state.old.version:
            raise SigningRotationBlocked("SIGNING_KEY_CUSTODY_CHANGED")
        facts = self.inventory(old, context)
        expected = {state.old.version.fingerprint, state.candidate.fingerprint}
        if any(key.fingerprint not in expected for key in facts.keys) or len(facts.keys) > 2:
            raise SigningRotationBlocked("SIGNING_KEY_SLOT_REVIEW")
        match = next(
            (key for key in facts.keys if key.fingerprint == state.candidate.fingerprint), None
        )
        if match is not None:
            if (
                match.state != "active"
                or match.created_at is None
                or not (state.candidate.material_created_at <= match.created_at <= self.clock())
            ):
                raise SigningRotationBlocked("SIGNING_KEY_UPLOAD_UNRECONCILED")
            uploaded = ManagedSigningKey(
                version=state.candidate,
                provider_key_id=match.provider_key_id,
                uploaded_at=match.created_at,
            )
            return self.save(
                state.model_copy(update={"phase": "verify", "uploaded": uploaded}), checkpoint
            )
        if state.upload_dispatched:
            raise SigningRotationBlocked("SIGNING_KEY_UPLOAD_UNRECONCILED")
        original = next(
            (key for key in facts.keys if key.provider_key_id == state.old.provider_key_id), None
        )
        if (
            original is None
            or original.fingerprint != state.old.version.fingerprint
            or original.state != "active"
        ):
            raise SigningRotationBlocked("SIGNING_KEY_CURRENT_UNVERIFIED")
        material = self.custody.material(state.candidate)
        if material.version != state.candidate:
            raise SigningRotationBlocked("SIGNING_KEY_CUSTODY_CHANGED")
        # This dispatch fence survives death after the provider accepted the upload.
        state = self.save(state.model_copy(update={"upload_dispatched": True}), checkpoint)
        mutation = SigningKeyMutation.model_validate(self.provider.upload(material, old, context))
        if mutation.effect == "none":
            state = self.save(state.model_copy(update={"upload_dispatched": False}), checkpoint)
            raise SigningRotationBlocked("SIGNING_KEY_UPLOAD_UNRECONCILED")
        # The next transition reads independent provider facts; mutation success alone is not proof.
        return state
