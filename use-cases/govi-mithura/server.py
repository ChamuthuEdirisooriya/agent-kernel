"""Run Govi Mithura through the Agent Kernel WhatsApp API integration."""

import logging
import re
from typing import Any

from agentkernel.api import RESTAPI

from agent import register_module
from whatsapp_runtime import build_whatsapp_handler

SENSITIVE_TOKEN_KEY = r"(?:hub(?:\.|_|%2e)verify_token|verify_token|access_token|appsecret_proof|token)"
SENSITIVE_QUERY_PATTERN = re.compile(rf"(?i)((?:{SENSITIVE_TOKEN_KEY})=)[^&\s\",)]+")
SENSITIVE_JSON_PATTERN = re.compile(rf"(?i)([\"']{SENSITIVE_TOKEN_KEY}[\"']\s*:\s*[\"'])[^\"']+([\"'])")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+")
SENSITIVE_ARGUMENT_KEY_PATTERN = re.compile(rf"(?i)^{SENSITIVE_TOKEN_KEY}$")
LONG_IDENTIFIER_PATTERN = re.compile(r"(?<!\d)\+?\d{7,25}(?!\d)")


def _redact_log_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    redacted = SENSITIVE_JSON_PATTERN.sub(r"\1[REDACTED]\2", value)
    redacted = SENSITIVE_QUERY_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", redacted)
    return LONG_IDENTIFIER_PATTERN.sub("[REDACTED_ID]", redacted)


class WhatsAppSensitiveDataFilter(logging.Filter):
    """Remove webhook secrets and payload content before configured log handlers render them."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = str(record.msg)
        if message.startswith("Received WhatsApp webhook:"):
            record.msg = "Received WhatsApp webhook payload [REDACTED]"
            record.args = ()
            return True
        if message.startswith("Message status update:"):
            record.msg = "Received WhatsApp message status update [REDACTED]"
            record.args = ()
            return True

        record.msg = _redact_log_value(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_log_value(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: "[REDACTED]" if SENSITIVE_ARGUMENT_KEY_PATTERN.fullmatch(str(key)) else _redact_log_value(value)
                for key, value in record.args.items()
            }
        return True


def install_sensitive_log_filters() -> None:
    """Install idempotent redaction on framework loggers that can receive WhatsApp identifiers."""
    for logger_name in ("uvicorn.access", "ak.api.whatsapp"):
        logger = logging.getLogger(logger_name)
        if not any(isinstance(existing, WhatsAppSensitiveDataFilter) for existing in logger.filters):
            logger.addFilter(WhatsAppSensitiveDataFilter())


def main() -> None:
    """Validate configuration and run the secured WhatsApp webhook server."""
    install_sensitive_log_filters()
    handler = build_whatsapp_handler()
    register_module()
    RESTAPI.run([handler])


if __name__ == "__main__":
    main()
