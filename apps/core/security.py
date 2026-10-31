"""Security headers middleware for ff-consumer."""

from __future__ import annotations


class SecurityHeadersMiddleware:
    """Inject security headers on every HTTP response."""

    _API_PATH_PREFIX = "/v1/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )

        if request.path.startswith(self._API_PATH_PREFIX):
            response.setdefault("Cache-Control", "no-store")

        return response
