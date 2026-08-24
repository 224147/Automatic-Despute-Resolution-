from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

from app.core.config import get_settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

SENSITIVE_KEYS = frozenset({
    "password", "token", "secret", "cvv", "pin", "card_number",
    "account_number", "ssn", "api_key", "authorization",
})


def _sanitize_event(_, __, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            event_dict[key] = "***REDACTED***"
    return event_dict


def _add_request_context(_, __, event_dict: dict) -> dict:
    rid = request_id_var.get("")
    cid = correlation_id_var.get("")
    if rid:
        event_dict["request_id"] = rid
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def setup_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_context,
        _sanitize_event,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or __name__)


def generate_request_id() -> str:
    return str(uuid.uuid4())
