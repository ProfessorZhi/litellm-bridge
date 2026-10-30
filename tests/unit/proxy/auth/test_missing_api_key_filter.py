"""Tests for the missing-API-key noise filter (PR #22, hand-ported onto 1.106.2).

The 1.100-era test files could not be reused verbatim: `tests/test_litellm/` was
reorganised into `tests/unit/` before 1.106.2, and `auth_exception_handler.py`
was rewritten upstream (quiet-log routing, `mark_invalid_virtual_key_error`,
`_with_client_context`). Everything below is either carried over unchanged
(the pure functions) or the same assertion the original PR made, re-anchored on
the 1.106.2 call shape.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import ProxyErrorTypes, ProxyException
from litellm.proxy.auth.auth_exception_handler import UserAPIKeyAuthExceptionHandler
from litellm.proxy.auth.missing_api_key import (
    MISSING_API_KEY_TOTAL_COUNTER_KEY,
    MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS,
    MissingAPIKeyError,
    record_missing_api_key_request,
    should_count_missing_api_key_requests,
    should_suppress_missing_api_key_logs,
)

def test_missing_api_key_error_is_a_401_client_error():
    error = MissingAPIKeyError("No api key passed in.")

    assert MissingAPIKeyError.status_code == 401
    assert str(error) == "No api key passed in."


@pytest.mark.parametrize(
    "configured, expected",
    [(True, True), (False, False), (None, False), ("true", False)],
)
def test_suppress_flag_requires_explicit_true(configured, expected):
    assert should_suppress_missing_api_key_logs({"suppress_missing_api_key_logs": configured}) is expected
    assert should_suppress_missing_api_key_logs({"count_missing_api_key_requests": configured}) is False


@pytest.mark.parametrize(
    "configured, expected",
    [(True, True), (False, False), (None, False), ("true", False)],
)
def test_count_flag_requires_explicit_true(configured, expected):
    assert should_count_missing_api_key_requests({"count_missing_api_key_requests": configured}) is expected
    assert should_count_missing_api_key_requests({"suppress_missing_api_key_logs": configured}) is False


@pytest.mark.asyncio
async def test_record_increments_prometheus_counter():
    metric = MagicMock()

    await record_missing_api_key_request(SimpleNamespace(litellm_missing_api_key_requests_metric=metric), None)

    metric.inc.assert_called_once_with()


@pytest.mark.asyncio
async def test_record_increments_redis_total_counter():
    cache = MagicMock()
    cache.async_increment = AsyncMock(return_value=1)

    await record_missing_api_key_request(None, cache)

    cache.async_increment.assert_awaited_once_with(
        MISSING_API_KEY_TOTAL_COUNTER_KEY,
        1,
        ttl=MISSING_API_KEY_TOTAL_COUNTER_TTL_SECONDS,
    )


@pytest.mark.asyncio
async def test_record_swallows_counter_failures_and_still_tries_redis():
    metric = MagicMock()
    metric.inc.side_effect = RuntimeError("prometheus broken")
    cache = MagicMock()
    cache.async_increment = AsyncMock(side_effect=ConnectionError("redis down"))

    await record_missing_api_key_request(SimpleNamespace(litellm_missing_api_key_requests_metric=metric), cache)

    metric.inc.assert_called_once_with()
    cache.async_increment.assert_awaited_once()


# ---- handler-level tests, lifted from the 1.100 PR test file from line 761 on ----

def _missing_api_key_error():
    from litellm.proxy.auth.missing_api_key import MissingAPIKeyError

    return MissingAPIKeyError("No api key passed in.")


async def _handle_missing_api_key(handler, error):
    with (
        patch(
            "litellm.proxy.proxy_server.proxy_logging_obj.post_call_failure_hook",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("litellm.proxy.auth.auth_exception_handler.seed_request_identity"),
        patch(
            "litellm.proxy.proxy_server.general_settings",
            {
                "allow_requests_on_db_unavailable": False,
                "suppress_missing_api_key_logs": True,
                "count_missing_api_key_requests": False,
            },
        ),
    ):
        with pytest.raises(ProxyException) as exc_info:
            await handler._handle_authentication_error(
                error,
                MagicMock(),
                {"model": "mock-chat"},
                "/v1/chat/completions",
                None,
                "sk-bad-key",
            )
    return exc_info.value


@pytest.mark.asyncio
async def test_missing_api_key_suppressed_keeps_401_without_console_error(caplog):
    """Suppression may only silence the log, never change the auth contract."""
    handler = UserAPIKeyAuthExceptionHandler()

    verbose_proxy_logger.propagate = True
    try:
        with caplog.at_level("DEBUG", logger="LiteLLM Proxy"):
            raised = await _handle_missing_api_key(handler, _missing_api_key_error())
    finally:
        verbose_proxy_logger.propagate = False

    assert int(raised.code) == status.HTTP_401_UNAUTHORIZED
    assert raised.message == "Authentication Error, No api key passed in."
    assert not [record for record in caplog.records if "user_api_key_auth(): Exception occured" in record.getMessage()]


@pytest.mark.asyncio
async def test_missing_api_key_logged_when_suppression_disabled(caplog):
    """The default must stay byte-for-byte the pre-change behaviour."""
    handler = UserAPIKeyAuthExceptionHandler()

    with (
        patch(
            "litellm.proxy.proxy_server.proxy_logging_obj.post_call_failure_hook",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("litellm.proxy.auth.auth_exception_handler.seed_request_identity"),
        patch(
            "litellm.proxy.proxy_server.general_settings",
            {
                "allow_requests_on_db_unavailable": False,
                "suppress_missing_api_key_logs": False,
            },
        ),
    ):
        verbose_proxy_logger.propagate = True
        try:
            with caplog.at_level("ERROR", logger="LiteLLM Proxy"), pytest.raises(ProxyException):
                await handler._handle_authentication_error(
                    _missing_api_key_error(),
                    MagicMock(),
                    {"model": "mock-chat"},
                    "/v1/chat/completions",
                    None,
                    "sk-bad-key",
                )
        finally:
            verbose_proxy_logger.propagate = False

    records = [r for r in caplog.records if "user_api_key_auth(): Exception occured" in r.getMessage()]
    assert len(records) == 1


@pytest.mark.asyncio
async def test_suppression_does_not_hide_other_auth_errors(caplog):
    """An unknown key is a real failure and must keep its error log."""
    handler = UserAPIKeyAuthExceptionHandler()

    with (
        patch(
            "litellm.proxy.proxy_server.proxy_logging_obj.post_call_failure_hook",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("litellm.proxy.auth.auth_exception_handler.seed_request_identity"),
        patch(
            "litellm.proxy.proxy_server.general_settings",
            {
                "allow_requests_on_db_unavailable": False,
                "suppress_missing_api_key_logs": True,
            },
        ),
    ):
        verbose_proxy_logger.propagate = True
        try:
            with caplog.at_level("ERROR", logger="LiteLLM Proxy"), pytest.raises(ProxyException):
                await handler._handle_authentication_error(
                    ProxyException(
                        message="Authentication Error, Invalid proxy server token passed.",
                        type=ProxyErrorTypes.token_not_found_in_db,
                        param="key",
                        code=status.HTTP_401_UNAUTHORIZED,
                    ),
                    MagicMock(),
                    {"model": "mock-chat"},
                    "/v1/chat/completions",
                    None,
                    "sk-unknown",
                )
        finally:
            verbose_proxy_logger.propagate = False

    records = [r for r in caplog.records if "user_api_key_auth(): Exception occured" in r.getMessage()]
    assert len(records) == 1


@pytest.mark.asyncio
async def test_missing_api_key_counted_once_when_enabled():
    handler = UserAPIKeyAuthExceptionHandler()

    with (
        patch(
            "litellm.proxy.proxy_server.proxy_logging_obj.post_call_failure_hook",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("litellm.proxy.auth.auth_exception_handler.seed_request_identity"),
        patch(
            "litellm.proxy.auth.auth_exception_handler.record_missing_api_key_request",
            new_callable=AsyncMock,
        ) as record,
        patch(
            "litellm.proxy.proxy_server.general_settings",
            {
                "allow_requests_on_db_unavailable": False,
                "suppress_missing_api_key_logs": False,
                "count_missing_api_key_requests": True,
            },
        ),
    ):
        with pytest.raises(ProxyException):
            await handler._handle_authentication_error(
                _missing_api_key_error(),
                MagicMock(),
                {"model": "mock-chat"},
                "/v1/chat/completions",
                None,
                "sk-bad-key",
            )

    record.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_api_key_not_counted_when_disabled():
    handler = UserAPIKeyAuthExceptionHandler()

    with (
        patch(
            "litellm.proxy.proxy_server.proxy_logging_obj.post_call_failure_hook",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("litellm.proxy.auth.auth_exception_handler.seed_request_identity"),
        patch(
            "litellm.proxy.auth.auth_exception_handler.record_missing_api_key_request",
            new_callable=AsyncMock,
        ) as record,
        patch(
            "litellm.proxy.proxy_server.general_settings",
            {
                "allow_requests_on_db_unavailable": False,
                "count_missing_api_key_requests": False,
            },
        ),
    ):
        with pytest.raises(ProxyException):
            await handler._handle_authentication_error(
                _missing_api_key_error(),
                MagicMock(),
                {"model": "mock-chat"},
                "/v1/chat/completions",
                None,
                "sk-bad-key",
            )

    record.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_factory, suppress, expect_failure_hook",
    [
        (_missing_api_key_error, True, False),
        (_missing_api_key_error, False, True),
        (lambda: Exception("Invalid proxy server token passed."), True, True),
    ],
)
async def test_suppression_skips_failure_hook_only_for_missing_api_key(error_factory, suppress, expect_failure_hook):
    """The failure hook writes the SpendLogs row; only a suppressed missing-key rejection may skip it."""
    handler = UserAPIKeyAuthExceptionHandler()
    failure_hook = AsyncMock(return_value=None)

    with (
        patch("litellm.proxy.proxy_server.proxy_logging_obj.post_call_failure_hook", failure_hook),
        patch("litellm.proxy.auth.auth_exception_handler.seed_request_identity"),
        patch(
            "litellm.proxy.proxy_server.general_settings",
            {"allow_requests_on_db_unavailable": False, "suppress_missing_api_key_logs": suppress},
        ),
    ):
        with pytest.raises(ProxyException) as exc_info:
            await handler._handle_authentication_error(
                error_factory(), MagicMock(), {"model": "mock-chat"}, "/v1/chat/completions", None, ""
            )

    assert int(exc_info.value.code) == status.HTTP_401_UNAUTHORIZED
    assert failure_hook.await_count == (1 if expect_failure_hook else 0)


@pytest.mark.asyncio
async def test_count_flag_does_not_count_other_auth_errors():
    handler = UserAPIKeyAuthExceptionHandler()

    with (
        patch(
            "litellm.proxy.proxy_server.proxy_logging_obj.post_call_failure_hook",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("litellm.proxy.auth.auth_exception_handler.seed_request_identity"),
        patch(
            "litellm.proxy.auth.auth_exception_handler.record_missing_api_key_request",
            new_callable=AsyncMock,
        ) as record,
        patch(
            "litellm.proxy.proxy_server.general_settings",
            {"allow_requests_on_db_unavailable": False, "count_missing_api_key_requests": True},
        ),
    ):
        with pytest.raises(ProxyException):
            await handler._handle_authentication_error(
                Exception("Invalid proxy server token passed."),
                MagicMock(),
                {"model": "mock-chat"},
                "/v1/chat/completions",
                None,
                "sk-bad-key",
            )

    record.assert_not_awaited()
