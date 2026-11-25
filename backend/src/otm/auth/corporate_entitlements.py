"""Explicit issuer dispatch for current Atlas grants after authentication."""

from pydantic import TypeAdapter

from otm.auth.corporate_enrollment import EnrollmentTarget, Guid


# Keep Atlas authorization current without querying OCI during an issued session.
class CorporateEntitlements:
    # Register distinct local and corporate namespaces and the exact corporate workspace.
    def __init__(self, grants, local_issuer, target: EnrollmentTarget):
        if local_issuer == target.issuer:
            raise ValueError("CORPORATE_ISSUER_COLLISION")
        self.grants, self.local_issuer, self.target = grants, local_issuer, target

    # Validate the scope before asking the database for the active grant and revision.
    def require_admin(self, issuer, subject, workspace):
        if issuer == self.local_issuer:
            return self.grants.require_admin(issuer, subject, workspace)
        if issuer != self.target.issuer or workspace != self.target.workspace:
            raise PermissionError("ADMINISTRATOR_REQUIRED")
        guid = TypeAdapter(Guid).validate_python(subject)
        return self.grants.require_admin(issuer, guid, workspace)
