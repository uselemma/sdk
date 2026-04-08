from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from uselemma_tracing import (
    disable_debug_mode,
    enable_debug_mode,
    is_debug_mode_enabled,
    agent,
)
from uselemma_tracing.debug_mode import _lemma_debug


def _echo(value, ctx):
    ctx.on_complete(value)
    return value


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

@dataclass
class _FakeSpan:
    attributes: dict[str, Any] = field(default_factory=dict)
    ended: bool = False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.ended = True

    def record_exception(self, exc: BaseException) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass


class _FakeTracer:
    def start_span(self, name: str, *, context=None, attributes=None) -> _FakeSpan:
        return _FakeSpan(attributes=dict(attributes or {}))


# ---------------------------------------------------------------------------
# debug_mode module tests
# ---------------------------------------------------------------------------

class TestDebugMode:
    def setup_method(self):
        disable_debug_mode()
        os.environ.pop("LEMMA_DEBUG", None)

    def teardown_method(self):
        disable_debug_mode()
        os.environ.pop("LEMMA_DEBUG", None)

    def test_disabled_by_default(self):
        assert is_debug_mode_enabled() is False

    def test_enable_debug_mode(self):
        enable_debug_mode()
        assert is_debug_mode_enabled() is True

    def test_disable_debug_mode(self):
        enable_debug_mode()
        disable_debug_mode()
        assert is_debug_mode_enabled() is False

    def test_env_var_activates(self):
        os.environ["LEMMA_DEBUG"] = "true"
        assert is_debug_mode_enabled() is True

    def test_env_var_other_value_does_not_activate(self):
        os.environ["LEMMA_DEBUG"] = "1"
        assert is_debug_mode_enabled() is False

    def test_lemma_debug_logs_when_enabled(self, capsys):
        enable_debug_mode()
        _lemma_debug("trace-wrapper", "span started", run_id="abc")
        out = capsys.readouterr().out
        assert "[LEMMA:trace-wrapper] span started" in out
        assert "abc" in out

    def test_lemma_debug_logs_without_data(self, capsys):
        enable_debug_mode()
        _lemma_debug("processor", "shutdown called")
        out = capsys.readouterr().out
        assert "[LEMMA:processor] shutdown called" in out

    def test_lemma_debug_silent_when_disabled(self, capsys):
        _lemma_debug("trace-wrapper", "span started", run_id="abc")
        out = capsys.readouterr().out
        assert out == ""


# ---------------------------------------------------------------------------
# wrap_agent debug logging integration
# ---------------------------------------------------------------------------

class TestAgentDebugLogging:
    def setup_method(self):
        disable_debug_mode()

    def teardown_method(self):
        disable_debug_mode()

    def test_logs_span_started_when_debug_enabled(self, monkeypatch, capsys):
        monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _: _FakeTracer())
        enable_debug_mode()

        wrapped = agent("test-agent", lambda _ctx, v: v)
        wrapped("hello")

        out = capsys.readouterr().out
        assert "[LEMMA:trace-wrapper] span started" in out
        assert "test-agent" in out

    def test_no_logs_when_debug_disabled(self, monkeypatch, capsys):
        monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _: _FakeTracer())

        wrapped = agent("test-agent", lambda _ctx, v: v)
        wrapped("hello")

        out = capsys.readouterr().out
        assert out == ""

    def test_logs_on_complete_when_debug_enabled(self, monkeypatch, capsys):
        monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _: _FakeTracer())
        enable_debug_mode()

        wrapped = agent("test-agent", _echo)
        wrapped("hello")

        out = capsys.readouterr().out
        assert "complete called" in out

    def test_logs_error_end_when_debug_enabled(self, monkeypatch, capsys):
        monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _: _FakeTracer())
        enable_debug_mode()

        def boom(_ctx, _v):
            raise RuntimeError("boom")

        wrapped = agent("test-agent", boom)
        with pytest.raises(RuntimeError):
            wrapped("x")

        out = capsys.readouterr().out
        assert "span ended on error" in out

    async def test_async_logs_span_started_when_debug_enabled(self, monkeypatch, capsys):
        monkeypatch.setattr("uselemma_tracing.trace_wrapper.trace.get_tracer", lambda _: _FakeTracer())
        enable_debug_mode()

        async def handler(_ctx, v):
            return v

        wrapped = agent("async-agent", handler)
        await wrapped("hello")

        out = capsys.readouterr().out
        assert "[LEMMA:trace-wrapper] span started" in out
