"""Restricted OCI Identity Domains operations for the isolated development pilot."""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from configparser import Error as ConfigParserError
from pathlib import Path
from types import SimpleNamespace

import oci
from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from otm.auth.corporate_browser import LAPTOP_PILOT_ORIGIN
from otm.auth.corporate_enrollment import (
    FEDERATED_USER,
    CorporateLookup,
    DomainPerson,
    Enrollment,
    Guid,
    NewAccountName,
    federated_user_request,
)
from otm.contracts import Contract, Text
from otm.operations.contracts import canonical_hash
from otm.platform_auth import api_key_signer, private_text, reject_public_oci_profile
from otm.storage.corporate_administrators import CorporateAdministrators, FederatedCreateConflict

LOGGER = logging.getLogger(__name__)
USER_ATTRIBUTES = "id,domainOcid,userName,displayName,active,deleteInProgress," + FEDERATED_USER
GROUP_ATTRIBUTES = "id,ocid,domainOcid,deleteInProgress,displayName"
GRANT_COLUMNS = (
    "id",
    "workspace_id",
    "identity_kind",
    "issuer",
    "subject",
    "display_name",
    "email",
    "status",
    "authorization_revision",
    "created_at",
    "updated_at",
    "revoked_at",
)
CALL_DEADLINE = 5
ENROLLMENT_IO = ThreadPoolExecutor(max_workers=2, thread_name_prefix="otm-enrollment")


# Require an explicit private writer registration for the 8445 runtime.
class LaptopEnrollmentConfiguration(Contract):
    # Absolute or home-relative path to a private OCI configuration file for the scoped writer.
    config_file: Text
    # Named profile (1–256 characters) for the development-only enrollment principal.
    profile: Text
    # Require an explicit opt-in to the same 8445 application signer for enrollment and readiness.
    use_application_profile: bool = False
    # Defaults to false. Enable account creation after provisioning and federation qualification.
    create_users: bool = False


# Bound how long a database transaction waits. Any dispatched write retains its hold in the worker.
def enrollment_io(operation, *arguments, hold=None):
    future = ENROLLMENT_IO.submit(operation, *arguments)
    try:
        return future.result(timeout=CALL_DEADLINE)
    except TimeoutError:
        if future.cancel() is True and hold is not None:
            hold.unlink()
        raise


# Map reads and two narrow write operations to one pinned OCI domain and group.
class LaptopEnrollment:
    # Keep unresolved writes fenced across restarts in the same private installation directory.
    def __init__(self, client, identity_client, tenancy, target, holds: Path):
        self.client, self.identity_client = client, identity_client
        self.tenancy, self.target, self.holds = tenancy, target, holds

    # Fail closed when a SCIM search response is incomplete or has unexpected pagination.
    def _rows(self, response):
        data = response.data
        rows = data.resources or []
        if type(data.total_results) is not int or data.total_results != len(rows):
            raise ValueError("INCOMPLETE_ENROLLMENT_LOOKUP")
        return rows

    # Project an exact account ID and provider lifecycle fields without retaining other attributes.
    def _person(self, user):
        extension = user.urn_ietf_params_scim_schemas_oracle_idcs_extension_user_user
        return DomainPerson(
            guid=user.id,
            domain=user.domain_ocid,
            username=user.user_name,
            display_name=user.display_name,
            active=user.active is True,
            federated=extension is not None and extension.is_federated_user is True,
            deleting=user.delete_in_progress is not None and user.delete_in_progress is not False,
        )

    # Use JSON string quoting for the SCIM literal and let the workflow enforce exact casing.
    def lookup(self, domain, email):
        if domain != self.target.domain:
            raise ValueError("ENROLLMENT_DOMAIN_MISMATCH")
        value = CorporateLookup(value=email).value
        if self._hold_path("create", value.casefold()).exists():
            raise ValueError("UNVERIFIED_ACCOUNT_CREATE_REQUIRES_RECONCILIATION")
        return enrollment_io(self._lookup, value)

    # Keep all remote lookup work within one caller deadline.
    def _lookup(self, value):
        response = self.client.list_users(
            filter=f"userName eq {json.dumps(value)}", count=2, attributes=USER_ATTRIBUTES
        )
        return tuple(self._person(user) for user in self._rows(response))

    # Create only the exact allowlisted federated record, holding any unresolved transport failure.
    def create(self, payload, retry_key):
        email = CorporateLookup(value=payload["userName"]).value
        name = payload.get("name")
        if not isinstance(name, dict):
            raise ValueError("UNSAFE_FEDERATED_USER_PAYLOAD")
        try:
            profile = NewAccountName(
                first_name=name.get("givenName"), last_name=name.get("familyName")
            )
        except ValueError:
            raise ValueError("UNSAFE_FEDERATED_USER_PAYLOAD") from None
        expected = federated_user_request(
            Enrollment(email=email, account=None, target=self.target), profile
        )
        if payload != expected:
            raise ValueError("UNSAFE_FEDERATED_USER_PAYLOAD")
        hold = self._hold("create", email.casefold())
        return enrollment_io(self._create, hold, payload, retry_key, hold=hold)

    # Clear the reservation only when OCI returns a definite outcome.
    def _create(self, hold, payload, retry_key):
        try:
            response = self.client.create_user(
                user=payload, opc_retry_token=retry_key, attributes=USER_ATTRIBUTES
            )
        except oci.exceptions.ServiceError as error:
            if error.status == 409:
                hold.unlink()
                raise FederatedCreateConflict() from None
            self._release_rejected(hold, error)
            raise
        except (oci.exceptions.ConnectTimeout, oci.exceptions.RequestException):
            raise TimeoutError("FEDERATED_CREATE_UNCERTAIN") from None
        account = self._person(response.data)
        login = payload["userName"]
        [confirmed] = self._lookup(login)
        if not (
            confirmed.guid == account.guid
            and confirmed.domain == account.domain == self.target.domain
            and confirmed.username == account.username == login
            and confirmed.federated
            and account.federated
            and confirmed.active
            and account.active
            and not confirmed.deleting
            and not account.deleting
        ):
            raise ValueError("UNVERIFIED_ACCOUNT_CREATE_REQUIRES_RECONCILIATION")
        hold.unlink()
        return confirmed

    # Identify an operation without putting a user identifier in the filename.
    def _hold_path(self, operation, subject):
        return self.holds / (canonical_hash({"kind": operation, "subject": subject}) + ".pending")

    # Reserve a single operation before a write so a lost response cannot race an opposite write.
    def _hold(self, operation, subject):
        hold = self._hold_path(operation, subject)
        hold.touch(mode=0o600, exist_ok=False)
        return hold

    # A definitive rejection can release the fence without claiming the write succeeded.
    def _release_rejected(self, hold, error):
        if error.status in {400, 401, 403, 404, 412, 429}:
            hold.unlink()

    # Verify presence with a complete exact-member search instead of relying on embedded lists.
    def _member(self, guid):
        response = self.client.list_groups(
            filter=f'id eq "{self.target.group}" and members.value eq "{guid}"',
            count=2,
            attributes="id",
        )
        rows = self._rows(response)
        if not rows:
            return False
        if len(rows) != 1 or rows[0].id != self.target.group:
            raise ValueError("ENROLLMENT_GROUP_MISMATCH")
        return True

    # Fence the exact same GUID across adds, removals and process restarts.
    def membership(self, group, guid, add, *, authorize=None):
        if group != self.target.group:
            raise ValueError("ENROLLMENT_GROUP_MISMATCH")
        if type(add) is not bool:
            raise ValueError("UNSAFE_ENROLLMENT_MEMBERSHIP_DIRECTION")
        guid = TypeAdapter(Guid).validate_python(guid)
        hold = self._hold_path("membership", guid)
        self._reserve_membership(hold, group, guid)
        try:
            group_ocid, user_ocid, entry, state = enrollment_io(
                self._membership_target, group, guid
            )
            if state is not None and state is not add and authorize is not None:
                authorize()
        except Exception:
            hold.unlink()
            LOGGER.warning("OCI enrollment membership preflight failed")
            raise
        if state is None or state is add:
            hold.unlink()
            return state is add
        return enrollment_io(
            self._membership, hold, group_ocid, user_ocid, entry, guid, add, hold=hold
        )

    # Clear an acknowledged hold only after both OCI views confirm the recorded direction.
    def _reserve_membership(self, hold, group, guid):
        try:
            hold.touch(mode=0o600, exist_ok=False)
        except FileExistsError:
            previous = hold.read_text()
            if previous not in ("add", "remove") or not enrollment_io(
                self._settled_membership, group, guid, previous == "add"
            ):
                raise
            hold.unlink()
            hold.touch(mode=0o600, exist_ok=False)

    # Complete bounded read-only preflight before the caller may authorize and dispatch a write.
    def _membership_target(self, group, guid):
        group_ocid, user_ocid = self._group_ocid(group), self._user_ocid(guid)
        entry, state = self._membership_state(group_ocid, user_ocid, guid)
        return group_ocid, user_ocid, entry, state

    # Dispatch only the approved native mutation and fence uncertain write or readback outcomes.
    def _membership(self, hold, group_ocid, user_ocid, entry, guid, add):
        action = "add" if add else "remove"
        try:
            if add:
                self.identity_client.add_user_to_group(
                    oci.identity.models.AddUserToGroupDetails(
                        group_id=group_ocid, user_id=user_ocid
                    )
                )
            else:
                self.identity_client.remove_user_from_group(entry.id)
        except oci.exceptions.ServiceError as error:
            LOGGER.warning("OCI enrollment membership %s rejected (HTTP %s)", action, error.status)
            self._release_rejected(hold, error)
            raise
        except Exception:
            LOGGER.warning("OCI enrollment membership %s outcome uncertain", action)
            raise
        try:
            confirmed = self._membership_state(group_ocid, user_ocid, guid)[1] is add
        except Exception:
            LOGGER.warning("OCI enrollment membership %s readback failed", action)
            confirmed = False
        if confirmed:
            hold.unlink()
            return True
        LOGGER.warning("OCI enrollment membership %s did not pass readback", action)
        hold.write_text(action)
        return False

    # Check both APIs so an acknowledged but transitioning write cannot release the fence.
    def _settled_membership(self, group, guid, add):
        group_ocid, user_ocid = self._group_ocid(group), self._user_ocid(guid)
        return self._membership_state(group_ocid, user_ocid, guid)[1] is add

    # Return a state only when native lifecycle and the SSO-facing directory agree.
    def _membership_state(self, group, user, guid):
        entry = self._native_membership(group, user)
        visible = self._member(guid)
        if entry is None and not visible:
            return None, False
        if entry is not None and entry.lifecycle_state == "ACTIVE" and visible:
            return entry, True
        return entry, None

    # Resolve the exact verified domain GUID to the native user OCID without an email lookup.
    def _user_ocid(self, guid):
        response = self.client.list_users(
            filter=f"id eq {json.dumps(guid)}", count=2, attributes="id,ocid,domainOcid"
        )
        [user] = self._rows(response)
        if user.id != guid or user.domain_ocid != self.target.domain:
            raise ValueError("ENROLLMENT_USER_MISMATCH")
        return self._oci_id(user.ocid, "user")

    # Validate the exact OCI association from the filtered and complete native response.
    def _native_membership(self, group, user):
        response = self.identity_client.list_user_group_memberships(
            self.tenancy, group_id=group, user_id=user, limit=2
        )
        if response.next_page or len(response.data) > 1:
            raise ValueError("ENROLLMENT_MEMBERSHIP_AMBIGUOUS")
        if not response.data:
            return None
        [entry] = response.data
        if entry.group_id != group or entry.user_id != user or entry.compartment_id != self.tenancy:
            raise ValueError("ENROLLMENT_MEMBERSHIP_MISMATCH")
        self._oci_id(entry.id, "groupmembership")
        return entry

    # Confirm scope against the domain API before passing a native group OCID to OCI IAM.
    def _group_ocid(self, group):
        response = self.client.get_group(group, attributes=GROUP_ATTRIBUTES)
        deleted = response.data.delete_in_progress
        if (
            response.data.id != group
            or response.data.domain_ocid != self.target.domain
            or response.data.display_name != "otm-development-users"
            or (deleted is not None and deleted is not False)
        ):
            raise ValueError("ENROLLMENT_GROUP_MISMATCH")
        return self._oci_id(response.data.ocid, "group")

    # Reject untyped, malformed or unexpected OCI identifiers before any native API call.
    def _oci_id(self, value, kind):
        if not isinstance(value, str) or not re.fullmatch(
            rf"ocid1[.]{kind}[.]oc[0-9]+[.][a-z0-9-]*[.][a-z0-9]{{1,220}}", value
        ):
            raise ValueError("ENROLLMENT_NATIVE_ID_INVALID")
        return value

    # Verify readiness with one exact group read, without needing GetTenancy authority.
    def check_scope(self):
        enrollment_io(self._group_ocid, self.target.group)


# Detect a pre-upgrade runtime role before any provider write can leave an orphan assignment.
def laptop_database_accepts_grants(store):
    try:
        with store.engine.connect() as connection:
            insert_allowed = (
                connection.scalar(
                    text(
                        "SELECT bool_and(has_column_privilege(current_user, "
                        "'public.otm_administrator', grant_column, 'INSERT')) "
                        "FROM unnest(CAST(:columns AS text[])) AS grant_column"
                    ),
                    {"columns": list(GRANT_COLUMNS)},
                )
                is True
            )
            update_allowed = (
                connection.scalar(
                    text(
                        "SELECT bool_and(has_column_privilege(current_user, "
                        "'public.otm_administrator', grant_column, 'UPDATE')) "
                        "FROM unnest(CAST(:columns AS text[])) AS grant_column"
                    ),
                    {"columns": ["group_cleanup_complete", "display_name", "email"]},
                )
                is True
            )
            return insert_allowed and update_allowed
    except SQLAlchemyError:
        return False


# Read the optional registration independently so startup can enforce public custody exclusion.
def read_enrollment_configuration(directory):
    try:
        return LaptopEnrollmentConfiguration.model_validate_json(
            private_text(directory / "corporate-enrollment.json")
        )
    except (OSError, ValueError):
        return None


# Mount only after checking the runtime database and read access to the exact OCI group.
def read_laptop_enrollment(directory, corporate, settings, store, frontend):
    config = read_enrollment_configuration(directory)
    if config is None:
        return None
    reject_public_oci_profile(config, frontend)
    try:
        identity = laptop_enrollment_identity(config, corporate, settings, frontend)
    except (OSError, ValueError, ConfigParserError, oci.exceptions.ClientError):
        return None
    if identity is None:
        return None
    if not laptop_database_accepts_grants(store):
        return None
    if (
        Path(identity.client_config["key_file"])
        .expanduser()
        .resolve()
        .is_relative_to(frontend.resolve())
    ):
        return None
    holds = directory / "corporate-enrollment-holds"
    try:
        holds.mkdir(mode=0o700, exist_ok=True)
        if (
            holds.is_symlink()
            or holds.stat().st_mode & 0o077
            or holds.stat().st_uid != os.geteuid()
        ):
            return None
    except OSError:
        return None
    try:
        client = oci.identity_domains.IdentityDomainsClient(
            identity.client_config,
            service_endpoint=corporate.oidc.provider_origin,
            signer=identity.signer,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(1, 2),
            log_requests=False,
        )
        iam = oci.identity.IdentityClient(
            dict(identity.client_config),
            signer=identity.signer,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(1, 2),
            log_requests=False,
        )
        adapter = LaptopEnrollment(client, iam, settings.oci.tenancy_ocid, corporate.target, holds)
        adapter.check_scope()
    except Exception:
        return None
    return CorporateAdministrators(
        store,
        corporate.target,
        adapter.lookup,
        adapter.membership,
        adapter.create if config.create_users else None,
    )


# Select the explicit scoped application signer without loading an operator credential.
def laptop_enrollment_identity(config, corporate, settings, frontend):
    policy = settings.oci
    private_config = Path(config.config_file).expanduser().resolve()
    if private_config.is_relative_to(frontend.resolve()):
        return None
    if config.use_application_profile:
        if (
            settings.environment != "local"
            or policy.auth_method != "api_key_profile"
            or corporate.target.environment != "development"
            or corporate.oidc.installation_origin != LAPTOP_PILOT_ORIGIN
            or config.profile != policy.profile
            or private_config != Path(policy.config_file).expanduser().resolve()
        ):
            return None
        return api_key_signer(policy)
    if config.profile == policy.profile:
        return None
    identity = api_key_signer(
        SimpleNamespace(
            config_file=config.config_file,
            profile=config.profile,
            tenancy_ocid=policy.tenancy_ocid,
            region=policy.region,
        )
    )
    readiness = api_key_signer(policy)
    if (
        identity.client_config["user"] == readiness.client_config["user"]
        or identity.client_config["fingerprint"] == readiness.client_config["fingerprint"]
    ):
        return None
    return identity
