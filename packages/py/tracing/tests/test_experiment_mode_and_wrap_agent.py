from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from opentelemetry.context import Context

from uselemma_tracing import (
    disable_experiment_mode,
    enable_experiment_mode,
    is_experiment_mode_enabled,
    wrap_agent,
)


def _echo(ctx, value):
    ctx.on_complete(value)
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


def test_wrap_agent_uses_root_ai_agent_run_and_global_or_local_experiment(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    disable_experiment_mode()
    assert is_experiment_mode_enabled() is False

    wrapped = wrap_agent("demo-agent", _echo, is_experiment=False)
    result, _run_id, _span = wrapped("hello")
    assert result == "hello"
    assert tracer.last_name == "ai.agent.run"
    assert isinstance(tracer.last_context, Context)
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["ai.agent.name"] == "demo-agent"
    assert tracer.last_attributes["lemma.is_experiment"] is False

    wrapped_local = wrap_agent("demo-agent", _echo, is_experiment=True)
    wrapped_local("hello")
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is True

    wrapped_local("hello", {"is_experiment": False})
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is False

    enable_experiment_mode()
    assert is_experiment_mode_enabled() is True

    wrapped_global = wrap_agent("demo-agent", _echo, is_experiment=False)
    wrapped_global("hello")
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is True

    disable_experiment_mode()


def test_wrap_agent_sets_thread_id_from_invocation_options(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped = wrap_agent("demo-agent", _echo)
    wrapped("hello", {"thread_id": "thread_123"})

    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.thread_id"] == "thread_123"


def test_wrap_agent_ignores_empty_thread_id_from_invocation_options(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped = wrap_agent("demo-agent", _echo)
    wrapped("hello", {"thread_id": "   "})

    assert tracer.last_attributes is not None
    assert "lemma.thread_id" not in tracer.last_attributes


def test_span_stays_open_without_on_complete(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped = wrap_agent("demo-agent", lambda _ctx, value: value)
    _, _, span = wrapped("hello")
    assert span.ended is False


def test_on_complete_sets_output_span_still_ends_once(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(ctx, value):
        ctx.on_complete("done")
        return value

    wrapped = wrap_agent("demo-agent", handler)
    _, _, span = wrapped("hello")
    assert span.attributes.get("ai.agent.output") == '"done"'
    assert span.ended is True


def test_on_complete_called_twice_first_output_wins(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(ctx, value):
        ctx.on_complete("a")
        ctx.on_complete("b")
        return value

    wrapped = wrap_agent("demo-agent", handler)
    _, _, span = wrapped("hello")
    assert span.attributes.get("ai.agent.output") == '"a"'
    assert span.ended is True


async def test_on_complete_ends_span_before_fn_returns(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    gate = asyncio.Event()

    async def async_handler(ctx, value):
        ctx.on_complete("done")
        await gate.wait()
        return value

    wrapped = wrap_agent("async-agent", async_handler)
    task = asyncio.create_task(wrapped("hello"))
    await asyncio.sleep(0)
    assert tracer.last_span is not None
    assert tracer.last_span.ended is True
    gate.set()
    await task


async def test_wrap_agent_async_agent(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    async def async_handler(ctx, value):
        out = value.upper()
        ctx.on_complete(out)
        return out

    wrapped = wrap_agent("async-agent", async_handler)
    result, run_id, span = await wrapped("hello")
    assert result == "HELLO"
    assert isinstance(run_id, str)
    assert tracer.last_name == "ai.agent.run"
    assert tracer.last_attributes["ai.agent.name"] == "async-agent"


def test_record_error_records_exception_and_sets_status(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(ctx, _value):
        ctx.record_error(Exception("boom"))
        ctx.on_complete("ok")
        return "ok"

    wrapped = wrap_agent("demo-agent", handler)
    result, _, span = wrapped("x")
    assert result == "ok"
    assert len(span.record_exception_calls) == 1
    assert str(span.record_exception_calls[0]) == "boom"
    assert len(span.set_status_calls) == 1


def test_record_error_wraps_non_exception_in_exception(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(ctx, _value):
        ctx.record_error("not an exception")
        ctx.on_complete("ok")
        return "ok"

    wrapped = wrap_agent("demo-agent", handler)
    result, _, span = wrapped("x")
    assert result == "ok"
    assert len(span.record_exception_calls) == 1
    assert isinstance(span.record_exception_calls[0], Exception)
    assert str(span.record_exception_calls[0]) == "not an exception"


def test_wrap_agent_sync_error_path(monkeypatch):
    tracer = _FakeTracer()
    spans_created = []

    def capturing_start_span(name, *, context=None, attributes=None):
        s = _FakeSpan(attributes=dict(attributes or {}))
        spans_created.append(s)
        return s

    tracer.start_span = capturing_start_span
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    def handler(_ctx, _value):
        raise ValueError("sync boom")

    wrapped = wrap_agent("demo-agent", handler)
    with pytest.raises(ValueError, match="sync boom"):
        wrapped("x")

    assert len(spans_created) == 1
    assert len(spans_created[0].record_exception_calls) == 1
    assert "sync boom" in str(spans_created[0].record_exception_calls[0])
    assert len(spans_created[0].set_status_calls) == 1
    assert spans_created[0].ended is True


async def test_wrap_agent_async_error_path(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    async def handler(_ctx, _value):
        raise RuntimeError("async boom")

    wrapped = wrap_agent("async-agent", handler)
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
