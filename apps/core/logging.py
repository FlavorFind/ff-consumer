"""Structured JSON logging for ff-consumer."""

import contextvars
import json
import logging
import traceback

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class RequestIDFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, self.datefmt),
        }
        if record.exc_info:
            log_data["exception"] = traceback.format_exception(*record.exc_info)
        if hasattr(record, "request_id") and record.request_id:
            log_data["request_id"] = record.request_id
        return json.dumps(log_data)
