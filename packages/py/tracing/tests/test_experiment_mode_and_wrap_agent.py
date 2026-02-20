from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.ended = True

    def record_exception(self, _exc: BaseException) -> None:
        return None

    def set_status(self, _status: Any) -> None:
        return None


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

    disable_experiment_mode()
