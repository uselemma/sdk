"""Tests for span helper call forms: decorator, named decorator, wrapper call, bare wrapper call."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator
from unittest.mock import patch

import pytest

from uselemma_tracing.span_helpers import llm, retrieval, tool, trace


# ---------------------------------------------------------------------------
# Fake OTel plumbing
# ---------------------------------------------------------------------------

@dataclass
class _FakeSpan:
    name: str
    record_exception_calls: list[BaseException] = field(default_factory=list)
    status_calls: list = field(default_factory=list)
    ended: bool = False

    def record_exception(self, exc: BaseException) -> None:
        self.record_exception_calls.append(exc)

    def set_status(self, status: Any) -> None:
        self.status_calls.append(status)

    def end(self) -> None:
        self.ended = True


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    @contextmanager
    def start_as_current_span(self, name: str) -> Iterator[_FakeSpan]:
        span = _FakeSpan(name=name)
        self.spans.append(span)
        try:
            yield span
        finally:
            span.ended = True


@pytest.fixture()
def fake_tracer(monkeypatch):
    tracer = _FakeTracer()
    monkeypatch.setattr("uselemma_tracing.span_helpers.otel_trace.get_tracer", lambda _: tracer)
    return tracer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last_span(fake_tracer: _FakeTracer) -> _FakeSpan:
    assert fake_tracer.spans, "No spans were created"
    return fake_tracer.spans[-1]


# ---------------------------------------------------------------------------
# trace() — no prefix
# ---------------------------------------------------------------------------

class TestTrace:
    def test_bare_decorator_uses_function_name(self, fake_tracer):
        @trace
        def my_fn(x):
            return x * 2

        assert my_fn(3) == 6
        assert _last_span(fake_tracer).name == "my_fn"

    def test_named_decorator_uses_given_name(self, fake_tracer):
        @trace("custom-name")
        def my_fn(x):
            return x + 1

        assert my_fn(5) == 6
        assert _last_span(fake_tracer).name == "custom-name"

    def test_wrapper_call_named(self, fake_tracer):
        def raw(x):
            return x.upper()

        wrapped = trace("shout", raw)
        assert wrapped("hello") == "HELLO"
        assert _last_span(fake_tracer).name == "shout"

    def test_wrapper_call_bare(self, fake_tracer):
        def raw(x):
            return x[::-1]

        wrapped = trace(raw)
        assert wrapped("abc") == "cba"
        assert _last_span(fake_tracer).name == "raw"

    async def test_async_named_decorator(self, fake_tracer):
        @trace("async-op")
        async def my_async_fn(x):
            return x * 3

        assert await my_async_fn(4) == 12
        assert _last_span(fake_tracer).name == "async-op"

    async def test_async_wrapper_call(self, fake_tracer):
        async def raw(x):
            return x + 10

        wrapped = trace("add-ten", raw)
        assert await wrapped(5) == 15
        assert _last_span(fake_tracer).name == "add-ten"

    def test_error_is_recorded_and_reraised(self, fake_tracer):
        @trace("boom-op")
        def boom():
            raise ValueError("oops")

        with pytest.raises(ValueError, match="oops"):
            boom()

        span = _last_span(fake_tracer)
        assert len(span.record_exception_calls) == 1
        assert str(span.record_exception_calls[0]) == "oops"
        assert len(span.status_calls) == 1

    async def test_async_error_is_recorded_and_reraised(self, fake_tracer):
        @trace("async-boom")
        async def boom():
            raise RuntimeError("async oops")

        with pytest.raises(RuntimeError, match="async oops"):
            await boom()

        span = _last_span(fake_tracer)
        assert len(span.record_exception_calls) == 1
        assert len(span.status_calls) == 1


# ---------------------------------------------------------------------------
# tool() — tool. prefix
# ---------------------------------------------------------------------------

class TestTool:
    def test_named_decorator_prefixes_span(self, fake_tracer):
        @tool("get-weather")
        def get_weather(city: str):
            return f"sunny in {city}"

        assert get_weather("London") == "sunny in London"
        assert _last_span(fake_tracer).name == "tool.get-weather"

    def test_wrapper_call_prefixes_span(self, fake_tracer):
        def get_weather(city: str):
            return f"rainy in {city}"

        wrapped = tool("get-weather", get_weather)
        assert wrapped("Paris") == "rainy in Paris"
        assert _last_span(fake_tracer).name == "tool.get-weather"

    def test_bare_decorator_uses_function_name_with_prefix(self, fake_tracer):
        @tool
        def lookup_order(order_id: str):
            return {"id": order_id}

        assert lookup_order("123") == {"id": "123"}
        assert _last_span(fake_tracer).name == "tool.lookup_order"

    async def test_async_wrapper_call(self, fake_tracer):
        async def fetch_data(key: str):
            return f"data:{key}"

        wrapped = tool("fetch-data", fetch_data)
        assert await wrapped("abc") == "data:abc"
        assert _last_span(fake_tracer).name == "tool.fetch-data"

    async def test_async_named_decorator(self, fake_tracer):
        @tool("search-db")
        async def search(query: str):
            return [query]

        assert await search("test") == ["test"]
        assert _last_span(fake_tracer).name == "tool.search-db"

    def test_error_propagates_with_prefix(self, fake_tracer):
        @tool("bad-tool")
        def bad():
            raise KeyError("missing")

        with pytest.raises(KeyError):
            bad()

        span = _last_span(fake_tracer)
        assert span.name == "tool.bad-tool"
        assert len(span.record_exception_calls) == 1


# ---------------------------------------------------------------------------
# llm() — llm. prefix
# ---------------------------------------------------------------------------

class TestLlm:
    def test_named_decorator_prefixes_span(self, fake_tracer):
        @llm("gpt-4o")
        def generate(prompt: str):
            return f"response to: {prompt}"

        assert generate("hi") == "response to: hi"
        assert _last_span(fake_tracer).name == "llm.gpt-4o"

    def test_wrapper_call_prefixes_span(self, fake_tracer):
        def generate(prompt: str):
            return prompt.upper()

        wrapped = llm("gpt-4o", generate)
        assert wrapped("hello") == "HELLO"
        assert _last_span(fake_tracer).name == "llm.gpt-4o"

    def test_bare_decorator_uses_function_name_with_prefix(self, fake_tracer):
        @llm
        def call_model(prompt: str):
            return "ok"

        call_model("test")
        assert _last_span(fake_tracer).name == "llm.call_model"

    async def test_async_wrapper_call(self, fake_tracer):
        async def generate(prompt: str):
            return f"async: {prompt}"

        wrapped = llm("claude-3", generate)
        assert await wrapped("hi") == "async: hi"
        assert _last_span(fake_tracer).name == "llm.claude-3"

    def test_error_propagates_with_prefix(self, fake_tracer):
        wrapped = llm("failing-model", lambda _: (_ for _ in ()).throw(RuntimeError("timeout")))

        with pytest.raises(RuntimeError, match="timeout"):
            wrapped("prompt")

        span = _last_span(fake_tracer)
        assert span.name == "llm.failing-model"
        assert len(span.record_exception_calls) == 1


# ---------------------------------------------------------------------------
# retrieval() — retrieval. prefix
# ---------------------------------------------------------------------------

class TestRetrieval:
    def test_named_decorator_prefixes_span(self, fake_tracer):
        @retrieval("vector-search")
        def search(query: str):
            return [f"doc:{query}"]

        assert search("cats") == ["doc:cats"]
        assert _last_span(fake_tracer).name == "retrieval.vector-search"

    def test_wrapper_call_prefixes_span(self, fake_tracer):
        def search(query: str):
            return []

        wrapped = retrieval("vector-search", search)
        wrapped("dogs")
        assert _last_span(fake_tracer).name == "retrieval.vector-search"

    def test_bare_decorator_uses_function_name_with_prefix(self, fake_tracer):
        @retrieval
        def semantic_search(query: str):
            return []

        semantic_search("test")
        assert _last_span(fake_tracer).name == "retrieval.semantic_search"

    async def test_async_wrapper_call(self, fake_tracer):
        async def search(query: str):
            return [query]

        wrapped = retrieval("async-search", search)
        assert await wrapped("x") == ["x"]
        assert _last_span(fake_tracer).name == "retrieval.async-search"


# ---------------------------------------------------------------------------
# Span lifecycle — span is always ended, even on error
# ---------------------------------------------------------------------------

class TestSpanLifecycle:
    def test_span_ends_on_success(self, fake_tracer):
        wrapped = tool("ok-tool", lambda x: x)
        wrapped("hi")
        assert _last_span(fake_tracer).ended is True

    def test_span_ends_on_error(self, fake_tracer):
        def boom(x):
            raise ValueError("boom")

        wrapped = tool("bad-tool", boom)
        with pytest.raises(ValueError):
            wrapped("x")

        assert _last_span(fake_tracer).ended is True

    async def test_async_span_ends_on_success(self, fake_tracer):
        async def fn(x):
            return x

        wrapped = llm("model", fn)
        await wrapped("hi")
        assert _last_span(fake_tracer).ended is True

    async def test_async_span_ends_on_error(self, fake_tracer):
        async def boom(x):
            raise RuntimeError("async boom")

        wrapped = llm("model", boom)
        with pytest.raises(RuntimeError):
            await wrapped("x")

        assert _last_span(fake_tracer).ended is True


# ---------------------------------------------------------------------------
# Return value is passed through unchanged
# ---------------------------------------------------------------------------

class TestReturnValue:
    def test_sync_return_value_unchanged(self, fake_tracer):
        data = {"key": "value", "num": 42}
        wrapped = tool("data-tool", lambda: data)
        assert wrapped() is data

    async def test_async_return_value_unchanged(self, fake_tracer):
        data = [1, 2, 3]

        async def fn():
            return data

        wrapped = llm("model", fn)
        assert await wrapped() is data
