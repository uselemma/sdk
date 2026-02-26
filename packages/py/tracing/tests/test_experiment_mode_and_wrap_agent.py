from __future__ import annotations

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
        return _FakeSpan(attributes=dict(attributes or {}))


def test_wrap_agent_uses_root_ai_agent_run_and_global_or_local_experiment(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    disable_experiment_mode()
    assert is_experiment_mode_enabled() is False

    wrapped = wrap_agent("demo-agent", lambda _ctx, value: value, is_experiment=False)
    result, _run_id, _span = wrapped("hello")
    assert result == "hello"
    assert tracer.last_name == "ai.agent.run"
    assert isinstance(tracer.last_context, Context)
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["ai.agent.name"] == "demo-agent"
    assert tracer.last_attributes["lemma.is_experiment"] is False
    assert tracer.last_attributes["lemma.auto_end_root"] is False

    wrapped_local = wrap_agent("demo-agent", lambda _ctx, value: value, is_experiment=True)
    wrapped_local("hello")
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is True

    enable_experiment_mode()
    assert is_experiment_mode_enabled() is True

    wrapped_global = wrap_agent("demo-agent", lambda _ctx, value: value, is_experiment=False)
    wrapped_global("hello")
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.is_experiment"] is True

    wrapped_auto_end = wrap_agent(
        "demo-agent",
        lambda _ctx, value: value,
        auto_end_root=True,
    )
    wrapped_auto_end("hello")
    assert tracer.last_attributes is not None
    assert tracer.last_attributes["lemma.auto_end_root"] is True

    disable_experiment_mode()


def test_on_complete_only_ends_when_auto_end_root_is_disabled(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    wrapped_manual = wrap_agent(
        "demo-agent",
        lambda ctx, value: (ctx.on_complete("done"), value),
        auto_end_root=False,
    )
    (ended_manual, _), _, span_manual = wrapped_manual("hello")
    assert ended_manual is True
    assert span_manual.ended is True

    wrapped_auto = wrap_agent(
        "demo-agent",
        lambda ctx, value: (ctx.on_complete("done"), value),
        auto_end_root=True,
    )
    (ended_auto, _), _, span_auto = wrapped_auto("hello")
    assert ended_auto is False
    assert span_auto.ended is False


async def test_wrap_agent_async_agent(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _name: tracer)

    async def async_handler(_ctx, value):
        return value.upper()

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
