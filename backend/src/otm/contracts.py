"""Shared closed model and timestamp/value primitives for production application contracts."""

from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints


# Reject undeclared/coerced fields and revalidate instances at trust boundaries.
#
# These internal messages contain identifiers and evidence references, never credentials,
# SDK kwargs or raw provider errors. Hiding validation inputs is defense in depth, not a
# promise that exception dictionaries or arbitrary strings are safe to log.
class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )


# Reject whitespace-only identifiers without silently rewriting their scope.
def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("A nonblank value is required")
    return value


# Require an explicit UTC instant, matching the reviewed execution wire contract.
def utc_only(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamps are required")
    return value


Text = Annotated[str, StringConstraints(min_length=1, max_length=256), AfterValidator(nonblank)]
UtcInstant = Annotated[AwareDatetime, AfterValidator(utc_only)]
Generation = Annotated[int, Field(ge=1)]


# Validate one server-configured HTTPS origin, never a client-supplied transport/host hint.
def canonical_https_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc != parsed.netloc.lower()
        or parsed.geturl() != value
        or parsed.netloc.endswith(":")
        or parsed.port == 443
    ):
        raise ValueError("A canonical HTTPS origin without path or default port is required")
    return value


HttpsOrigin = Annotated[Text, AfterValidator(canonical_https_origin)]
