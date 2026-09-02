"""Tests for secret-safe WhatsApp server logging."""

import logging

import pytest

from server import WhatsAppSensitiveDataFilter, install_sensitive_log_filters


def test_sensitive_log_filter_redacts_verify_token_and_long_identifiers() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1",
            "GET",
            "/whatsapp/webhook?hub.verify_token=super-secret-token&hub.challenge=1234567890123",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert WhatsAppSensitiveDataFilter().filter(record) is True
    rendered = record.getMessage()

    assert "super-secret-token" not in rendered
    assert "1234567890123" not in rendered
    assert "hub.verify_token=[REDACTED]" in rendered


def test_sensitive_log_filter_replaces_debug_webhook_payload() -> None:
    record = logging.LogRecord(
        name="ak.api.whatsapp",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg='Received WhatsApp webhook: {"from":"94770000001","text":{"body":"private message"}}',
        args=(),
        exc_info=None,
    )

    WhatsAppSensitiveDataFilter().filter(record)

    assert record.getMessage() == "Received WhatsApp webhook payload [REDACTED]"


def test_sensitive_log_filter_redacts_framework_bare_verify_token_log() -> None:
    record = logging.LogRecord(
        name="ak.api.whatsapp",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="Webhook verification request: mode=subscribe, token=super-secret-verify-token, challenge=1234567890",
        args=(),
        exc_info=None,
    )

    WhatsAppSensitiveDataFilter().filter(record)
    rendered = record.getMessage()

    assert "super-secret-verify-token" not in rendered
    assert "token=[REDACTED]" in rendered


@pytest.mark.parametrize(
    ("message", "secret"),
    [
        ('Message sent successfully: {"access_token": "secret-json-token"}', "secret-json-token"),
        ("Request headers: Authorization: Bearer secret-bearer-token", "secret-bearer-token"),
    ],
)
def test_sensitive_log_filter_redacts_json_and_bearer_tokens(message: str, secret: str) -> None:
    record = logging.LogRecord(
        name="ak.api.whatsapp",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )

    WhatsAppSensitiveDataFilter().filter(record)
    rendered = record.getMessage()

    assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_sensitive_log_filter_redacts_secret_mapping_arguments() -> None:
    record = logging.LogRecord(
        name="ak.api.whatsapp",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="Resolved access token: %(access_token)s",
        args=({"access_token": "secret-mapping-token"},),
        exc_info=None,
    )

    WhatsAppSensitiveDataFilter().filter(record)

    assert "secret-mapping-token" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_install_sensitive_log_filters_is_idempotent() -> None:
    logger_names = ("uvicorn.access", "ak.api.whatsapp")
    original_filters = {name: list(logging.getLogger(name).filters) for name in logger_names}
    try:
        install_sensitive_log_filters()
        install_sensitive_log_filters()

        for name in logger_names:
            matching = [
                item for item in logging.getLogger(name).filters if isinstance(item, WhatsAppSensitiveDataFilter)
            ]
            assert len(matching) == 1
    finally:
        for name in logger_names:
            logging.getLogger(name).filters = original_filters[name]
