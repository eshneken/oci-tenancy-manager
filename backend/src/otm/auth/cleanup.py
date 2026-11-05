"""Bounded session housekeeping; authentication expiration never waits for this job."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pydantic import TypeAdapter

from otm.contracts import Contract, UtcInstant
from otm.settings import SessionCleanupSettings


# Expose only invalid-session deletion, not identity or audit-table deletion.
class SessionPurger(Protocol):
    # Delete at most limit invalid rows in one short transaction and return their count.
    def purge_expired(self, at: datetime, limit: int) -> int: ...


# Retain aggregate housekeeping status without session identifiers or private data.
class CleanupResult(Contract):
    deleted: int
    batches: int
    batch_limit_reached: bool


# Limit work per run; a later scheduled run can safely resume any remaining invalid rows.
def cleanup_sessions(
    repository: SessionPurger, settings: SessionCleanupSettings, clock: Callable[[], datetime]
) -> CleanupResult:
    settings = SessionCleanupSettings.model_validate(settings)
    total = 0
    for batch in range(1, settings.max_batches + 1):
        count = repository.purge_expired(
            TypeAdapter(UtcInstant).validate_python(clock()), settings.batch_size
        )
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 0 <= count <= settings.batch_size
        ):
            raise ValueError("INVALID_SESSION_CLEANUP_COUNT")
        total += count
        if count < settings.batch_size:
            return CleanupResult(deleted=total, batches=batch, batch_limit_reached=False)
    return CleanupResult(deleted=total, batches=settings.max_batches, batch_limit_reached=True)
