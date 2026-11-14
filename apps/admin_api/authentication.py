"""
Service token authentication for the Consumer Admin API.

FFCC sends:  Authorization: Bearer <ADMIN_API_SERVICE_TOKEN>

The token is compared using secrets.compare_digest (constant-time) against
settings.ADMIN_API_SERVICE_TOKEN.  A blank token in settings means the
endpoint is effectively locked down (all requests rejected).

A synthetic ServiceUser is returned — it has is_authenticated=True and
is_staff=True but is not a real database user, so it must never be used
as a FK.  Views use it only for permission checks and audit logging.
"""

import secrets

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ServiceUser:
    """Lightweight user-like object returned by ServiceTokenAuthentication."""

    is_authenticated = True
    is_staff = True
    is_anonymous = False
    pk = None

    def __str__(self):
        return "FFCC Service"


class ServiceTokenAuthentication(BaseAuthentication):
    """
    Authenticate requests that carry a valid ADMIN_API_SERVICE_TOKEN.

    Header format:
        Authorization: Bearer <token>
    """

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None  # Let DRF try other authenticators or return 401.

        token = auth_header[len("Bearer "):]
        expected = getattr(settings, "ADMIN_API_SERVICE_TOKEN", "")

        if not expected:
            raise AuthenticationFailed(
                "Admin API service token is not configured on this server."
            )

        # Constant-time comparison — prevents timing attacks.
        if not secrets.compare_digest(token.strip(), expected.strip()):
            raise AuthenticationFailed("Invalid service token.")

        return (ServiceUser(), token)

    def authenticate_header(self, request):
        return "Bearer"
