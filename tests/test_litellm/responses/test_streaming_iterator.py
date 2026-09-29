"""Regression tests for LIT-4185 — /v1/responses streaming must stamp
completion_start_time on the first chunk so downstream TTFT consumers
(Prometheus, OTEL, SpendLogs completionStartTime) do not fall back to
completion_start_time = end_time."""

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from typing import Final
from unittest.mock import Mock

import httpx
import pytest

import litellm
from litellm.integrations.custom_logger import CustomLogger
from litellm.litellm_core_utils.litellm_logging import Logging as LiteLLMLoggingObj
from litellm.llms.base_llm.responses.transformation import BaseResponsesAPIConfig
from litellm.responses.streaming_iterator import (
    ResponsesAPIStreamingIterator,
    SyncResponsesAPIStreamingIterator,
)
from litellm.types.llms.openai import (
    ResponseCompletedEvent,
    ResponsesAPIResponse,
    ResponsesAPIStreamEvents,
)


def _sse_event(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _mock_config() -> Mock:
    mock_config = Mock(spec=BaseResponsesAPIConfig)
    mock_responses_api_response = Mock(spec=ResponsesAPIResponse)
    mock_responses_api_response.id = "resp_ttft"

    def _transform(model, parsed_chunk, logging_obj):
        evt_type = parsed_chunk.get("type")
        if evt_type == "response.completed":
            completed = Mock(spec=ResponseCompletedEvent)
            completed.type = ResponsesAPIStreamEvents.RESPONSE_COMPLETED
            completed.response = mock_responses_api_response
            return completed
        stub = Mock()
        stub.type = evt_type
        return stub

    mock_config.transform_streaming_response.side_effect = _transform
    return mock_config


def _make_iterator(
    *,
    sse_events: list[bytes],
    logging_obj: LiteLLMLoggingObj,
    trailing_error: Exception | None = None,
) -> ResponsesAPIStreamingIterator:
    async def aiter_bytes():
        for evt in sse_events:
            yield evt
        if trailing_error is not None:
            raise trailing_error

    mock_response = Mock()
    mock_response.headers = {}
    mock_response.aiter_bytes = aiter_bytes

    return ResponsesAPIStreamingIterator(
        response=mock_response,
        model="gpt-4o-mini",
        responses_api_provider_config=_mock_config(),
        logging_obj=logging_obj,
        litellm_metadata={},
        custom_llm_provider="openai",
    )


def _make_sync_iterator(
    *,
    sse_events: list[bytes],
    logging_obj: LiteLLMLoggingObj,
    trailing_error: Exception | None = None,
) -> SyncResponsesAPIStreamingIterator:
    def iter_bytes():
        for evt in sse_events:
            yield evt
        if trailing_error is not None:
            raise trailing_error

    mock_response = Mock()
    mock_response.headers = {}
    mock_response.iter_bytes = iter_bytes

    return SyncResponsesAPIStreamingIterator(
        response=mock_response,
        model="gpt-4o-mini",
        responses_api_provider_config=_mock_config(),
        logging_obj=logging_obj,
        litellm_metadata={},
        custom_llm_provider="openai",
    )


def _logging_obj_stub() -> Mock:
    logging_obj = Mock(spec=LiteLLMLoggingObj)
    logging_obj.completion_start_time = None
    logging_obj.model_call_details = {"litellm_params": {}}
    return logging_obj


@pytest.mark.asyncio
async def test_responses_streaming_stamps_completion_start_time_on_first_chunk():
    """Without the fix, `logging_obj.completion_start_time` stays None across the
    entire stream and _success_handler_helper_fn falls back to end_time — collapsing
    the reported TTFT to full generation time."""
    logging_obj = Mock(spec=LiteLLMLoggingObj)
    logging_obj.completion_start_time = None
    logging_obj.model_call_details = {"litellm_params": {}}
    stamped: list[datetime] = []

    def _update(*, completion_start_time):
        stamped.append(completion_start_time)
        logging_obj.completion_start_time = completion_start_time
        logging_obj.model_call_details["completion_start_time"] = completion_start_time

    logging_obj._update_completion_start_time.side_effect = _update

    iterator = _make_iterator(
        sse_events=[
            _sse_event({"type": "response.created"}),
            _sse_event({"type": "response.output_text.delta", "delta": "hi"}),
            _sse_event({"type": "response.completed"}),
        ],
        logging_obj=logging_obj,
    )

    async for _ in iterator:
        pass

    assert len(stamped) == 1, (
        f"Expected exactly one first-chunk stamp; got {len(stamped)}. "
        "Later chunks must not re-stamp completion_start_time."
    )
    assert isinstance(stamped[0], datetime)


@pytest.mark.asyncio
async def test_responses_streaming_does_not_reset_prior_completion_start_time():
    """If `completion_start_time` is already set (e.g. by an outer wrapper), the
    iterator must not overwrite it — otherwise TTFT would collapse to
    time-to-last-chunk under contention."""
    prior = datetime(2020, 1, 1, 0, 0, 0)
    logging_obj = Mock(spec=LiteLLMLoggingObj)
    logging_obj.completion_start_time = prior
    logging_obj.model_call_details = {"litellm_params": {}}

    iterator = _make_iterator(
        sse_events=[
            _sse_event({"type": "response.created"}),
            _sse_event({"type": "response.completed"}),
        ],
        logging_obj=logging_obj,
    )

    async for _ in iterator:
        pass

    logging_obj._update_completion_start_time.assert_not_called()
    assert logging_obj.completion_start_time == prior


_COMPLETE_STREAM_EVENTS = [
    _sse_event({"type": "response.created"}),
    _sse_event({"type": "response.output_text.delta", "delta": "hi"}),
    _sse_event({"type": "response.completed"}),
]

_PARTIAL_OUTPUT_EVENTS = [
    _sse_event({"type": "response.created"}),
    _sse_event({"type": "response.output_text.delta", "delta": "hi"}),
]

_TRAILING_ERRORS = [
    httpx.ReadError("Response payload is not completed"),
    httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("trailing_error", _TRAILING_ERRORS, ids=type)
async def test_transport_error_after_completed_event_ends_stream_cleanly(trailing_error):
    """A sloppy connection close after `response.completed` must not turn a
    complete stream into an error (regression guard for the transport no longer
    swallowing ClientPayloadError/TransferEncodingError)."""
    iterator = _make_iterator(
        sse_events=_COMPLETE_STREAM_EVENTS,
        logging_obj=_logging_obj_stub(),
        trailing_error=trailing_error,
    )

    seen = [event.type async for event in iterator]

    assert ResponsesAPIStreamEvents.RESPONSE_COMPLETED in seen


@pytest.mark.asyncio
async def test_transport_error_before_completed_event_raises():
    """A connection lost before any terminal event is a real failure and must
    surface, not end the stream as if it completed."""
    iterator = _make_iterator(
        sse_events=_COMPLETE_STREAM_EVENTS[:-1],
        logging_obj=_logging_obj_stub(),
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )

    with pytest.raises(httpx.ReadError):
        async for _ in iterator:
            pass


@pytest.mark.parametrize("trailing_error", _TRAILING_ERRORS, ids=type)
def test_sync_transport_error_after_completed_event_ends_stream_cleanly(trailing_error):
    iterator = _make_sync_iterator(
        sse_events=_COMPLETE_STREAM_EVENTS,
        logging_obj=_logging_obj_stub(),
        trailing_error=trailing_error,
    )

    seen = [event.type for event in iterator]

    assert ResponsesAPIStreamEvents.RESPONSE_COMPLETED in seen


def test_sync_transport_error_before_completed_event_raises():
    iterator = _make_sync_iterator(
        sse_events=_COMPLETE_STREAM_EVENTS[:-1],
        logging_obj=_logging_obj_stub(),
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )

    with pytest.raises(httpx.ReadError):
        for _ in iterator:
            pass


def test_stream_cache_write_completes_when_asyncio_run_closes_the_loop(monkeypatch):
    """
    Regression test for LIT-6184 on the /v1/responses streaming surface: the
    completed-stream cache write was dispatched as a bare fire-and-forget task,
    so asyncio.run cancelled it at loop close before the write landed. The
    write must survive loop shutdown just like the chat-completions one.
    """
    import asyncio
    from types import SimpleNamespace

    import litellm
    from litellm.types.utils import CallTypes

    writes = []

    class _SlowWriteCache:
        async def async_add_cache(self, result, dynamic_cache_object=None, **kwargs):
            await asyncio.sleep(0.2)
            writes.append(result)

        def add_cache(self, *args, **kwargs):
            raise AssertionError("sync write must not run on the async path")

    caching_handler = SimpleNamespace(
        request_kwargs={
            "model": "test-model",
            "input": "hello",
            "stream": True,
            "caching": True,
            "metadata": None,
            "custom_llm_provider": "openai",
        },
        preset_cache_key="responses-stream-cache-key",
        original_function=litellm.aresponses,
        dual_cache=None,
        _should_store_result_in_cache=lambda original_function, kwargs: True,
    )
    logging_obj = SimpleNamespace(
        model_call_details={"litellm_params": {}},
        _llm_caching_handler=caching_handler,
    )
    iterator = ResponsesAPIStreamingIterator(
        response=httpx.Response(200),
        model="test-model",
        responses_api_provider_config=Mock(spec=BaseResponsesAPIConfig),
        logging_obj=logging_obj,
        request_data=caching_handler.request_kwargs,
        call_type=CallTypes.aresponses.value,
    )
    iterator.completed_response = ResponseCompletedEvent(
        type=ResponsesAPIStreamEvents.RESPONSE_COMPLETED,
        response=ResponsesAPIResponse(
            id="resp_lit6184",
            created_at=int(datetime.now().timestamp()),
            status="completed",
            model="test-model",
            object="response",
            output=[],
        ),
    )
    monkeypatch.setattr(litellm, "cache", _SlowWriteCache())

    async def _short_lived_script():
        iterator._persist_completed_response_to_cache(is_async=True)

    asyncio.run(_short_lived_script())

    assert len(writes) == 1


class _LoopRecordingLogger(CustomLogger):
    def __init__(self) -> None:
        super().__init__()
        self.failure_loop: asyncio.AbstractEventLoop | None = None
        self.failure_deployment_id: str | None = None
        self.failure_finished = False
        self.hook_loop: asyncio.AbstractEventLoop | None = None
        self.hook_finished = False

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.failure_loop = asyncio.get_running_loop()
        self.failure_deployment_id = kwargs["litellm_params"].get("model_info", {}).get("id")
        await asyncio.sleep(0.05)
        self.failure_finished = True

    async def async_post_call_success_deployment_hook(self, request_data, response, call_type):
        self.hook_loop = asyncio.get_running_loop()
        await asyncio.sleep(0.05)
        self.hook_finished = True


class _SyncOnlyRecordingLogger(CustomLogger):
    def __init__(self) -> None:
        super().__init__()
        self.sync_failure_finished = False

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.sync_failure_finished = True


class _OrderRecordingSyncLogger(CustomLogger):
    def __init__(self, async_recorder: _LoopRecordingLogger) -> None:
        super().__init__()
        self._async_recorder: Final = async_recorder
        self.async_failure_finished_first: bool | None = None

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.async_failure_finished_first = self._async_recorder.failure_finished


def _real_logging_obj(*, call_type: str = "aresponses", litellm_params: dict | None = None) -> LiteLLMLoggingObj:
    logging_obj: Final = LiteLLMLoggingObj(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        call_type=call_type,
        start_time=datetime.now(),
        litellm_call_id="lit-0218-test",
        function_id="lit-0218-test",
    )
    logging_obj.model_call_details["litellm_params"] = (
        dict(litellm_params) if litellm_params is not None else {"aresponses": True}
    )
    return logging_obj


async def _wait_until(condition: Callable[[], bool]) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never became true")


@pytest.mark.asyncio
async def test_transport_error_failure_logging_runs_on_the_iterating_loop(monkeypatch):
    """A dropped provider stream used to run async_failure_handler through run_async_function,
    which builds a new loop in a worker thread and parks the iterating loop until it returns."""
    recorder: Final = _LoopRecordingLogger()
    monkeypatch.setattr(litellm, "_async_failure_callback", [recorder])
    monkeypatch.setattr(litellm, "failure_callback", [])
    iterator: Final = _make_iterator(
        sse_events=_PARTIAL_OUTPUT_EVENTS,
        logging_obj=_real_logging_obj(),
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )

    with pytest.raises(httpx.ReadError):
        async for _ in iterator:
            pass

    assert recorder.failure_finished is True
    assert recorder.failure_loop is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_failure_logging_can_await_state_bound_to_the_iterating_loop(monkeypatch):
    """The failure callback awaits state the request's own loop owns, the spend-update queue
    among it. Dispatched onto a foreign loop that await raises RuntimeError, which the caller
    swallows, so the failure never reaches the spend log."""
    spend_queue: asyncio.Queue = asyncio.Queue()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(spend_queue.get(), timeout=0.01)
    drained: list[object] = []

    class _QueueReadingLogger(CustomLogger):
        async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
            drained.append(await spend_queue.get())

    recorder: Final = _QueueReadingLogger()
    monkeypatch.setattr(litellm, "_async_failure_callback", [recorder])
    monkeypatch.setattr(litellm, "failure_callback", [])
    iterator: Final = _make_iterator(
        sse_events=_PARTIAL_OUTPUT_EVENTS,
        logging_obj=_real_logging_obj(),
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )

    async def _produce_the_pending_update() -> None:
        await asyncio.sleep(0.05)
        await spend_queue.put("spend-update")

    producer: Final = asyncio.create_task(_produce_the_pending_update())
    try:
        with pytest.raises(httpx.ReadError):
            async for _ in iterator:
                pass
    finally:
        producer.cancel()

    assert drained == ["spend-update"]


@pytest.mark.asyncio
async def test_failure_logging_does_not_park_the_iterating_loop(monkeypatch):
    """While the failure callback ran, the iterating loop served nothing else: a request
    failing mid-stream stalled every other request on that worker for as long as the
    callback took."""
    ticks: list[int] = []

    async def _ticker() -> None:
        while True:
            ticks.append(1)
            await asyncio.sleep(0.01)

    class _SlowFailureLogger(CustomLogger):
        async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
            await asyncio.sleep(0.1)

    monkeypatch.setattr(litellm, "_async_failure_callback", [_SlowFailureLogger()])
    monkeypatch.setattr(litellm, "failure_callback", [])
    iterator: Final = _make_iterator(
        sse_events=_PARTIAL_OUTPUT_EVENTS,
        logging_obj=_real_logging_obj(),
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )
    ticker: Final = asyncio.create_task(_ticker())
    await asyncio.sleep(0)
    try:
        with pytest.raises(httpx.ReadError):
            async for _ in iterator:
                pass
        ticks_while_failing: Final = len(ticks)
    finally:
        ticker.cancel()

    assert ticks_while_failing >= 3, f"the iterating loop only ran {ticks_while_failing} callbacks during failure logging"


@pytest.mark.asyncio
async def test_failure_logging_finishes_before_the_error_reaches_the_consumer(monkeypatch):
    """The router's mid-stream fallback re-enters the same logging object for the next
    deployment as soon as it catches the error, so failure logging that runs after the raise
    attributes the failure to the fallback deployment."""
    recorder: Final = _LoopRecordingLogger()
    monkeypatch.setattr(litellm, "_async_failure_callback", [recorder])
    monkeypatch.setattr(litellm, "failure_callback", [])
    logging_obj: Final = _real_logging_obj(
        litellm_params={"aresponses": True, "model_info": {"id": "primary-deployment"}}
    )
    iterator: Final = _make_iterator(
        sse_events=[],
        logging_obj=logging_obj,
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )

    with pytest.raises(httpx.ReadError):
        async for _ in iterator:
            pass
    logging_obj.model_call_details["litellm_params"]["model_info"] = {"id": "fallback-deployment"}

    assert recorder.failure_finished is True
    assert recorder.failure_deployment_id == "primary-deployment"


@pytest.mark.asyncio
async def test_sync_stream_failure_inside_a_running_loop_still_runs_sync_only_callbacks(monkeypatch):
    recorder: Final = _SyncOnlyRecordingLogger()
    monkeypatch.setattr(litellm, "failure_callback", [recorder])
    monkeypatch.setattr(litellm, "_async_failure_callback", [])
    iterator: Final = _make_sync_iterator(
        sse_events=_PARTIAL_OUTPUT_EVENTS,
        logging_obj=_real_logging_obj(call_type="responses", litellm_params={}),
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )

    with pytest.raises(httpx.ReadError):
        for _ in iterator:
            pass

    await _wait_until(lambda: recorder.sync_failure_finished)


@pytest.mark.asyncio
async def test_sync_failure_callbacks_run_after_async_failure_logging_finishes(monkeypatch):
    """Both handlers read the same logging object, so the sync one must not start while the
    async one is still running, which is the ordering the blocking dispatch used to give."""
    async_recorder: Final = _LoopRecordingLogger()
    sync_recorder: Final = _OrderRecordingSyncLogger(async_recorder)
    monkeypatch.setattr(litellm, "_async_failure_callback", [async_recorder])
    monkeypatch.setattr(litellm, "failure_callback", [sync_recorder])
    iterator: Final = _make_sync_iterator(
        sse_events=_PARTIAL_OUTPUT_EVENTS,
        logging_obj=_real_logging_obj(call_type="responses", litellm_params={}),
        trailing_error=httpx.ReadError("Response payload is not completed"),
    )

    with pytest.raises(httpx.ReadError):
        for _ in iterator:
            pass

    await _wait_until(lambda: sync_recorder.async_failure_finished_first is not None)

    assert sync_recorder.async_failure_finished_first is True


@pytest.mark.asyncio
async def test_completed_stream_success_deployment_hook_runs_on_the_iterating_loop(monkeypatch):
    recorder: Final = _LoopRecordingLogger()
    monkeypatch.setattr(litellm, "callbacks", [recorder])
    iterator: Final = _make_iterator(sse_events=_COMPLETE_STREAM_EVENTS, logging_obj=_logging_obj_stub())

    async for _ in iterator:
        pass

    assert recorder.hook_finished is True
    assert recorder.hook_loop is asyncio.get_running_loop()
