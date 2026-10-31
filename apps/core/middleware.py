"""Core middleware for ff-consumer."""

import uuid

from django.utils.deprecation import MiddlewareMixin

from apps.core.logging import request_id_var


class RequestIDMiddleware(MiddlewareMixin):
    """Attach a unique request ID to every request and response."""

    def process_request(self, request):
        request.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(request.request_id)

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", str(uuid.uuid4()))
        response["X-Request-ID"] = request_id
        return response
