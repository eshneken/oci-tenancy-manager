"""Corporate identity admission and bounded provisioning requests for the Atlas pilot."""

from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter, field_validator

from otm.contracts import Contract, Text
from otm.email_policy import mailbox
from otm.operations.contracts import canonical_hash

Guid = Annotated[
    str,
    StringConstraints(
        pattern=r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
    ),
]
FEDERATED_USER = "urn:ietf:params:scim:schemas:oracle:idcs:extension:user:User"
# Bound names after trimming and reject C0, DEL and C1 controls.
PersonName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f-\x9f]+$"
    ),
]


# Accept administrator-entered profile names for new accounts only, independent of login identity.
class NewAccountName(Contract):
    first_name: PersonName = Field(repr=False)
    last_name: PersonName = Field(repr=False)


# Accept only an exact email used as the domain login name.
class CorporateLookup(Contract):
    value: Annotated[str, StringConstraints(min_length=1, max_length=254)]

    # Preserve the local-part spelling so federation matching can be exact.
    @field_validator("value")
    @classmethod
    def normalize(cls, value: str) -> str:
        return mailbox(value.strip())


# Represent only the domain facts necessary to reuse an exact domain account.
class DomainPerson(Contract):
    guid: Guid
    domain: Text
    username: Text
    display_name: Text | None = None
    active: bool
    federated: bool
    deleting: bool


# Pin app/group and authorization scope on the server; no browser-supplied targeting.
class EnrollmentTarget(Contract):
    # Select exactly one installation and its grant scope.
    environment: Literal["development", "staging", "production"]
    # Database authorization scope, 1–256 nonblank characters.
    workspace: Text
    # Exact verified domain identifier, 1–256 nonblank characters.
    domain: Text
    # Internal corporate namespace, 1–256 nonblank characters, independent of the wire issuer.
    issuer: Text
    # Exact 32-hex or hyphenated GUID of this installation's assigned app.
    app: Guid
    # Exact 32-hex or hyphenated GUID of this installation's app-only group.
    group: Guid
    # Exact registered client ID, 1–256 nonblank characters, required for browser composition.
    oidc_client_id: Text | None = None


# Display the exact submitted email and optional OCI display name before confirmation.
class EnrollmentReview(Contract):
    environment: Literal["development", "staging", "production"]
    role: Literal["Administrator"] = "Administrator"
    username: str
    work_email: str
    display_name: str
    existing_account: bool


# Bind the entered email, target and matched account to the administrator's review.
class Enrollment(Contract):
    email: Text = Field(repr=False)
    target: EnrollmentTarget = Field(repr=False)
    account: DomainPerson | None = Field(repr=False)

    # Produce the fingerprint a confirmer can compare against newly verified evidence.
    def binding(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))

    # Allow the browser to review these specific values before it can confirm an intent.
    def review(self) -> EnrollmentReview:
        name = self.account.display_name if self.account else None
        return EnrollmentReview(
            environment=self.target.environment,
            username=self.email,
            work_email=self.email,
            display_name=name or self.email,
            existing_account=self.account is not None,
        )


# Refuse disabled, deleting or mismatched accounts. Existing OCI credentials are independent.
def verify_domain_person(target: EnrollmentTarget, email: str, account: DomainPerson):
    if (
        account.domain != target.domain
        or account.username != email
        or not account.active
        or account.deleting
    ):
        raise ValueError("CORPORATE_DOMAIN_BINDING_UNVERIFIED")


# Prepare a read-only review for an exact existing account or a new federated account.
def prepare_enrollment(
    lookup: CorporateLookup,
    target: EnrollmentTarget,
    domain_lookup: Callable[[str, str], tuple[DomainPerson, ...]],
) -> Enrollment:
    return Enrollment(
        email=lookup.value,
        target=target,
        account=read_domain_person(target, lookup.value, domain_lookup),
    )


# Use the same exact verified binding before and after an account creation attempt.
def read_domain_person(
    target: EnrollmentTarget,
    email: str,
    domain_lookup: Callable[[str, str], tuple[DomainPerson, ...]],
) -> DomainPerson | None:
    # Empty results are meaningful only for a complete successful read in this exact domain.
    accounts = domain_lookup(target.domain, email)
    if len(accounts) > 1:
        raise ValueError("CORPORATE_DOMAIN_BINDING_UNVERIFIED")
    account = DomainPerson.model_validate(accounts[0]) if accounts else None
    if account is not None:
        verify_domain_person(target, email, account)
    return account


# Build only the allowed OCI profile fields and keep the email as the exact federation login.
def federated_user_request(enrollment: Enrollment, name: NewAccountName) -> dict:
    email = CorporateLookup(value=enrollment.email).value
    if enrollment.account is not None:
        raise ValueError("CORPORATE_ACCOUNT_ALREADY_EXISTS")
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User", FEDERATED_USER],
        "userName": email,
        "displayName": f"{name.first_name} {name.last_name}",
        "name": {"givenName": name.first_name, "familyName": name.last_name},
        "emails": [{"value": email, "type": "work", "primary": True}],
        FEDERATED_USER: {"isFederatedUser": True, "bypassNotification": True},
    }


# Carry the exact installation, verified domain GUID and direction to the membership adapter.
def membership_request(target: EnrollmentTarget, guid: Guid, *, add: bool) -> tuple[str, str, bool]:
    return target.group, TypeAdapter(Guid).validate_python(guid), add
