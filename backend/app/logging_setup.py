"""Structured logging foundation: JSON output with recursive secret redaction."""

import logging
import re
import sys

import structlog

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"password|token|secret|authorization|cookie|content|answer|prompt",
    re.IGNORECASE,
)


def _is_sensitive(key: object) -> bool:
    return isinstance(key, str) and _SENSITIVE_KEY.search(key) is not None


def redact_sensitive(value: object) -> object:
    """Return a copy with values under sensitive keys masked; input untouched.

    Shared policy: structlog output and audit_log metadata redact identically.
    """
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive(key) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return value


def redact_processor(
    logger: object, method_name: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    """Pure structlog processor: mask any key matching the sensitive pattern.

    Recurses into nested dicts/lists and returns a new structure; the input
    event_dict is never mutated.
    """
    return redact_sensitive(event_dict)


def configure_logging(env: str) -> None:
    """Route structlog through the redaction processor to JSON on stdout."""
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
