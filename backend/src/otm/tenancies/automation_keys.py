"""Safe observational signing-key views derived from sealed checks, never credential heads."""

from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.contracts import Contract, Text, UtcInstant
from otm.providers.automation_keys import Fingerprint, key_age


# Each row reports public provider facts and a dated age assessment, never custody/compliance.
class AutomationKeyView(Contract):
    provider_key_id: Text
    fingerprint: Fingerprint
    created_at: UtcInstant | None
    key_state: Literal["active", "inactive", "unknown"]
    age_state: Literal["within_limit", "due_soon", "overdue", "unknown", "inactive"]
    age_days: int | None = Field(default=None, ge=0)
    retirement_due_at: UtcInstant | None = None


# A verified empty list and an unavailable inventory have different state/provenance semantics.
class AutomationKeysView(Contract):
    state: Literal["not_checked", "known", "unavailable", "stale"] = "not_checked"
    checked_at: UtcInstant | None = None
    age_as_of: UtcInstant | None = None
    operation_id: UUID | None = None
    keys: Annotated[tuple[AutomationKeyView, ...], Field(max_length=16)] = ()

    # Positive/empty qualified observations need actual dated provenance; unavailable has no rows.
    @model_validator(mode="after")
    def provenance(self):
        if self.state in {"known", "stale"} and (
            self.checked_at is None or self.age_as_of is None or self.operation_id is None
        ):
            raise ValueError("AUTOMATION_KEY_VIEW_UNQUALIFIED")
        if self.state not in {"known", "stale"} and self.keys:
            raise ValueError("AUTOMATION_KEY_VIEW_UNQUALIFIED")
        return self


# Assessment time is supplied explicitly: server read time for current views, capture for history.
def inventory_view(check, operation_id, at, *, stale=False):
    if check is None:
        return AutomationKeysView()
    if check.state != "known":
        return AutomationKeysView(
            state="unavailable", checked_at=check.checked_at, operation_id=operation_id
        )
    rows = []
    for key in check.keys:
        # A future-dated creation fact cannot become qualified just because time passes.
        assessed = (
            key
            if key.created_at is None or key.created_at <= check.checked_at
            else key.model_copy(update={"created_at": None})
        )
        status, due = key_age(assessed, at)
        rows.append(
            AutomationKeyView(
                provider_key_id=key.provider_key_id,
                fingerprint=key.fingerprint,
                created_at=key.created_at,
                key_state=key.state,
                age_state=status,
                age_days=int((at - key.created_at) / timedelta(days=1))
                if due is not None
                else None,
                retirement_due_at=due,
            )
        )
    return AutomationKeysView(
        state="stale" if stale else "known",
        checked_at=check.checked_at,
        age_as_of=at,
        operation_id=operation_id,
        keys=tuple(rows),
    )
