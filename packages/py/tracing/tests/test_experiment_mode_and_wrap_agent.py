from __future__ import annotations

import asyncio
import warnings
from dataclasses import dataclass, field
from typing import Any

import pytest
from opentelemetry.context import Context

from uselemma_tracing import (
    disable_experiment_mode,
    enable_experiment_mode,
    is_experiment_mode_enabled,
    agent,
    wrap_agent,  # deprecated alias — kept to verify backward compat
)


def _echo(value, ctx):
    ctx.complete(value)
    return value


@dataclass
class _FakeSpan:
    attributes: dict[str, Any] = field(default_factory=dict)
    ended: bool = False
    record_exception_calls: list = field(default_factory=list, repr=False)
    set_status_calls: list = field(default_factory=list, repr=False)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.ended = True

    def record_exception(self, exc: BaseException) -> None:
        self.record_exception_calls.append(exc)

    def set_status(self, status: Any) -> None:
        self.set_status_calls.append(status)


class _FakeTracer:
    def __init__(self) -> None:
        self.last_name: str | None = None
        self.last_context: Context | None = None
        self.last_attributes: dict[str, Any] | None = None
        self.last_span: _FakeSpan | None = None

    def start_span(
        self,
        name: str,
        *,
        context: Context | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> _FakeSpan:
        self.last_name = name
        self.last_context = context
        self.last_attributes = attributes
        span = _FakeSpan(attributes=dict(attributes or {}))
        self.last_span = span
        return span


def test_agent_uses_root_ai_agent_run_and_global_or_local_experiment(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    disable_experiment_mode()
    assert is_experiment_mode_enabled() is False

    wrapped = agent("demo-agent", _echo, is_experiment=False)
    result, _run_id, _span = wrapped("hello")
    assert result == "hello"
    assert tracer.last_name == "ai.agent.run"
    assert isinstance(tracer.last_context, Context)
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["ai.agent.name"] == "demo-agent"
    assert tracer.last_attributes["lemma.is_experiment"] is False

    wrapped_local = agent("demo-agent", _echo, is_experiment=True)
    wrapped_local("hello")
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is True

    wrapped_local("hello", {"is_experiment": False})
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is False

    enable_experiment_mode()
    assert is_experiment_mode_enabled() is True

    wrapped_global = agent("demo-agent", _echo, is_experiment=False)
    wrapped_global("hello")
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is True

    disable_experiment_mode()


def test_agent_sets_thread_id_from_invocation_options(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped = agent("demo-agent", _echo)
    wrapped("hello", {"thread_id": "thread_123"})

    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.thread_id"] == "thread_123"


def test_agent_ignores_empty_thread_id_from_invocation_options(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped = agent("demo-agent", _echo)
    wrapped("hello", {"thread_id": "   "})

    assert tracer.last_attributes is not None
    assert "lemma.thread_id" not in tracer.last_attributes


def test_span_auto_closes_and_captures_return_value(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped = agent("demo-agent", lambda value, _ctx: value)
    res = wrapped("hello")
    assert res.result == "hello"
    assert res.span.ended is True
    assert res.span.attributes.get("ai.agent.output") == '"hello"'


def test_explicit_complete_overrides_return_value(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(value, ctx):
        ctx.complete("explicit-output")
        return value

    wrapped = agent("demo-agent", handler)
    _, _, span = wrapped("hello")
    assert span.attributes.get("ai.agent.output") == '"explicit-output"'
    assert span.ended is True


def test_complete_called_twice_first_output_wins(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(value, ctx):
        ctx.complete("a")
        ctx.complete("b")
        return value

    wrapped = agent("demo-agent", handler)
    _, _, span = wrapped("hello")
    assert span.attributes.get("ai.agent.output") == '"a"'
    assert span.ended is True


async def test_complete_ends_span_before_fn_returns(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    gate = asyncio.Event()

    async def async_handler(value, ctx):
        ctx.complete("done")
        await gate.wait()
        return value

    wrapped = agent("async-agent", async_handler)
    task = asyncio.create_task(wrapped("hello"))
    await asyncio.sleep(0)
    assert tracer.last_span is not None
    assert tracer.last_span.ended is True
    gate.set()
    await task


async def test_agent_async(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    async def async_handler(value, _ctx):
        return value.upper()

    wrapped = agent("async-agent", async_handler)
    result, run_id, span = await wrapped("hello")
    assert result == "HELLO"
    assert isinstance(run_id, str)
    assert tracer.last_name == "ai.agent.run"
    assert tracer.last_attributes["ai.agent.name"] == "async-agent"
    assert span.ended is True
    assert span.attributes.get("ai.agent.output") == '"HELLO"'


def test_fail_records_exception_and_sets_status(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(_value, ctx):
        ctx.fail(Exception("boom"))
        return "ok"

    wrapped = agent("demo-agent", handler)
    result, _, span = wrapped("x")
    assert result == "ok"
    assert len(span.record_exception_calls) == 1
    assert str(span.record_exception_calls[0]) == "boom"
    assert len(span.set_status_calls) == 1


def test_fail_wraps_non_exception_in_exception(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(_value, ctx):
        ctx.fail("not an exception")
        return "ok"

    wrapped = agent("demo-agent", handler)
    result, _, span = wrapped("x")
    assert result == "ok"
    assert len(span.record_exception_calls) == 1
    assert isinstance(span.record_exception_calls[0], Exception)
    assert str(span.record_exception_calls[0]) == "not an exception"


def test_deprecated_on_complete_and_record_error_still_work(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(_value, ctx):
        ctx.record_error(Exception("boom"))
        ctx.on_complete("legacy-output")
        return "return-value"

    wrapped = agent("demo-agent", handler)
    result, _, span = wrapped("x")
    assert result == "return-value"
    assert span.attributes.get("ai.agent.output") == '"legacy-output"'
    assert len(span.record_exception_calls) == 1
    assert span.ended is True


def test_agent_sync_error_path(monkeypatch):
    tracer = _FakeTracer()
    spans_created = []

    def capturing_start_span(name, *, context=None, attributes=None):
        s = _FakeSpan(attributes=dict(attributes or {}))
        spans_created.append(s)
        return s

    tracer.start_span = capturing_start_span
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(_value, _ctx):
        raise ValueError("sync boom")

    wrapped = agent("demo-agent", handler)
    with pytest.raises(ValueError, match="sync boom"):
        wrapped("x")

    assert len(spans_created) == 1
    assert len(spans_created[0].record_exception_calls) == 1
    assert "sync boom" in str(spans_created[0].record_exception_calls[0])
    assert len(spans_created[0].set_status_calls) == 1
    assert spans_created[0].ended is True


async def test_agent_async_error_path(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    async def handler(_value, _ctx):
        raise RuntimeError("async boom")

    wrapped = agent("async-agent", handler)
    spans_created = []

    def capturing_start_span(name, *, context=None, attributes=None):
        s = _FakeSpan(attributes=dict(attributes or {}))
        spans_created.append(s)
        return s

    tracer.start_span = capturing_start_span

    with pytest.raises(RuntimeError, match="async boom"):
        await wrapped("x")

    assert len(spans_created) == 1
    assert len(spans_created[0].record_exception_calls) == 1
    assert "async boom" in str(spans_created[0].record_exception_calls[0])
    assert spans_created[0].ended is True


# ---------------------------------------------------------------------------
# Streaming mode
# ---------------------------------------------------------------------------

def test_streaming_span_stays_open_until_complete(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wrapped = agent("demo-agent", lambda value, _ctx: value, streaming=True)
        res = wrapped("hello")

    assert res.result == "hello"
    assert res.span.ended is False
    assert res.span.attributes.get("ai.agent.output") is None


def test_streaming_complete_closes_span(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(value, ctx):
        ctx.complete(f"out:{value}")
        return value

    wrapped = agent("demo-agent", handler, streaming=True)
    _, _, span = wrapped("hello")
    assert span.attributes.get("ai.agent.output") == '"out:hello"'
    assert span.ended is True


def test_streaming_emits_warning_when_complete_not_called(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped = agent("streaming-agent", lambda value, _ctx: value, streaming=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        wrapped("hello")
        assert len(w) == 1
        assert "streaming-agent" in str(w[0].message)


def test_streaming_no_warning_when_complete_is_called(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(value, ctx):
        ctx.complete(value)
        return value

    wrapped = agent("streaming-agent", handler, streaming=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        wrapped("hello")
        assert len(w) == 0


# ---------------------------------------------------------------------------
# Backward compatibility — wrap_agent is a deprecated alias for agent
# ---------------------------------------------------------------------------

def test_wrap_agent_deprecated_alias_still_works(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        wrapped = wrap_agent("demo-agent", _echo)
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "wrap_agent" in str(w[0].message)

    result, run_id, span = wrapped("hello")
    assert result == "hello"
    assert isinstance(run_id, str)
    assert span.ended is True
