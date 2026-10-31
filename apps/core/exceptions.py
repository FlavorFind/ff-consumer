"""Custom exception handling for the consumer API."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Return a consistent JSON error shape for all API errors."""
    response = exception_handler(exc, context)

    request = context.get("request")
    request_id = getattr(request, "request_id", None) if request else None

    if response is not None:
        error_data = {
            "error": {
                "code": _get_error_code(response.status_code),
                "message": _flatten_errors(response.data),
                "request_id": request_id,
            }
        }
        response.data = error_data
    else:
        logger.exception("Unhandled exception", exc_info=exc)
        response = Response(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "request_id": request_id,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def _get_error_code(status_code: int) -> str:
    codes = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        429: "rate_limit_exceeded",
        500: "internal_error",
    }
    return codes.get(status_code, "error")


def _flatten_errors(data) -> str:
    if isinstance(data, dict):
        messages = []
        for key, value in data.items():
            if key == "error":
                return _flatten_errors(value)
            if isinstance(value, list):
                messages.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                messages.append(str(value))
        return " | ".join(messages)
    if isinstance(data, list):
        return ", ".join(str(item) for item in data)
    return str(data)
