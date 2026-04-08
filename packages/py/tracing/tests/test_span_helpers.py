"""Tests for span helper call forms: decorator, named decorator, wrapper call, bare wrapper call."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import pytest

from uselemma_tracing.span_helpers import llm, retrieval, tool, trace


# ---------------------------------------------------------------------------
# Fake OTel plumbing
# ---------------------------------------------------------------------------

@dataclass
class _FakeSpan:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    record_exception_calls: list[BaseException] = field(default_factory=list)
    status_calls: list = field(default_factory=list)
    ended: bool = False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

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
# trace() — no span.type attribute, but I/O captured
# ---------------------------------------------------------------------------

class TestTrace:
    def test_bare_decorator_uses_function_name(self, fake_tracer):
        @trace
        def my_fn(x):
            return x * 2

        assert my_fn(3) == 6
        span = _last_span(fake_tracer)
        assert span.name == "my_fn"
        assert "span.type" not in span.attributes

    def test_named_decorator_uses_given_name(self, fake_tracer):
        @trace("custom-name")
        def my_fn(x):
            return x + 1

        assert my_fn(5) == 6
        span = _last_span(fake_tracer)
        assert span.name == "custom-name"
        assert "span.type" not in span.attributes

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

    def test_input_and_output_captured(self, fake_tracer):
        @trace("echo")
        def echo(x):
            return x * 2

        echo(21)
        span = _last_span(fake_tracer)
        assert json.loads(span.attributes["input.value"]) == 21
        assert json.loads(span.attributes["output.value"]) == 42

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
# tool() — span.type = "tool", I/O captured
# ---------------------------------------------------------------------------

class TestTool:
    def test_named_decorator_sets_span_type(self, fake_tracer):
        @tool("get-weather")
        def get_weather(city: str):
            return f"sunny in {city}"

        assert get_weather("London") == "sunny in London"
        span = _last_span(fake_tracer)
        assert span.name == "get-weather"
        assert span.attributes["span.type"] == "tool"

    def test_wrapper_call_sets_span_type(self, fake_tracer):
        def get_weather(city: str):
            return f"rainy in {city}"

        wrapped = tool("get-weather", get_weather)
        assert wrapped("Paris") == "rainy in Paris"
        span = _last_span(fake_tracer)
        assert span.name == "get-weather"
        assert span.attributes["span.type"] == "tool"

    def test_bare_decorator_uses_function_name(self, fake_tracer):
        @tool
        def lookup_order(order_id: str):
            return {"id": order_id}

        assert lookup_order("123") == {"id": "123"}
        span = _last_span(fake_tracer)
        assert span.name == "lookup_order"
        assert span.attributes["span.type"] == "tool"

    def test_input_and_output_captured(self, fake_tracer):
        @tool("get-weather")
        def get_weather(city: str):
            return {"temp": 22, "city": city}

        get_weather("London")
        span = _last_span(fake_tracer)
        assert json.loads(span.attributes["input.value"]) == "London"
        assert json.loads(span.attributes["output.value"]) == {"temp": 22, "city": "London"}

    async def test_async_wrapper_call(self, fake_tracer):
        async def fetch_data(key: str):
            return f"data:{key}"

        wrapped = tool("fetch-data", fetch_data)
        assert await wrapped("abc") == "data:abc"
        span = _last_span(fake_tracer)
        assert span.name == "fetch-data"
        assert span.attributes["span.type"] == "tool"

    async def test_async_named_decorator(self, fake_tracer):
        @tool("search-db")
        async def search(query: str):
            return [query]

        assert await search("test") == ["test"]
        span = _last_span(fake_tracer)
        assert span.name == "search-db"
        assert span.attributes["span.type"] == "tool"

    def test_error_propagates(self, fake_tracer):
        @tool("bad-tool")
        def bad():
            raise KeyError("missing")

        with pytest.raises(KeyError):
            bad()

        span = _last_span(fake_tracer)
        assert span.name == "bad-tool"
        assert span.attributes["span.type"] == "tool"
        assert len(span.record_exception_calls) == 1

    def test_output_not_set_on_error(self, fake_tracer):
        @tool("bad-tool")
        def bad(x: str):
            raise ValueError("boom")

        with pytest.raises(ValueError):
            bad("input")

        span = _last_span(fake_tracer)
        assert "input.value" in span.attributes
        assert "output.value" not in span.attributes


# ---------------------------------------------------------------------------
# llm() — span.type = "generation", I/O captured
# ---------------------------------------------------------------------------

class TestLlm:
    def test_named_decorator_sets_span_type(self, fake_tracer):
        @llm("gpt-4o")
        def generate(prompt: str):
            return f"response to: {prompt}"

        assert generate("hi") == "response to: hi"
        span = _last_span(fake_tracer)
        assert span.name == "gpt-4o"
        assert span.attributes["span.type"] == "generation"

    def test_wrapper_call_sets_span_type(self, fake_tracer):
        def generate(prompt: str):
            return prompt.upper()

        wrapped = llm("gpt-4o", generate)
        assert wrapped("hello") == "HELLO"
        span = _last_span(fake_tracer)
        assert span.name == "gpt-4o"
        assert span.attributes["span.type"] == "generation"

    def test_bare_decorator_uses_function_name(self, fake_tracer):
        @llm
        def call_model(prompt: str):
            return "ok"

        call_model("test")
        span = _last_span(fake_tracer)
        assert span.name == "call_model"
        assert span.attributes["span.type"] == "generation"

    def test_input_and_output_captured(self, fake_tracer):
        @llm("gpt-4o")
        def generate(prompt: str):
            return "the answer"

        generate("what is 2+2?")
        span = _last_span(fake_tracer)
        assert json.loads(span.attributes["input.value"]) == "what is 2+2?"
        assert json.loads(span.attributes["output.value"]) == "the answer"

    async def test_async_wrapper_call(self, fake_tracer):
        async def generate(prompt: str):
            return f"async: {prompt}"

        wrapped = llm("claude-3", generate)
        assert await wrapped("hi") == "async: hi"
        span = _last_span(fake_tracer)
        assert span.name == "claude-3"
        assert span.attributes["span.type"] == "generation"

    def test_error_propagates(self, fake_tracer):
        wrapped = llm("failing-model", lambda _: (_ for _ in ()).throw(RuntimeError("timeout")))

        with pytest.raises(RuntimeError, match="timeout"):
            wrapped("prompt")

        span = _last_span(fake_tracer)
        assert span.name == "failing-model"
        assert span.attributes["span.type"] == "generation"
        assert len(span.record_exception_calls) == 1


# ---------------------------------------------------------------------------
# retrieval() — span.type = "retriever", I/O captured
# ---------------------------------------------------------------------------

class TestRetrieval:
    def test_named_decorator_sets_span_type(self, fake_tracer):
        @retrieval("vector-search")
        def search(query: str):
            return [f"doc:{query}"]

        assert search("cats") == ["doc:cats"]
        span = _last_span(fake_tracer)
        assert span.name == "vector-search"
        assert span.attributes["span.type"] == "retriever"

    def test_wrapper_call_sets_span_type(self, fake_tracer):
        def search(query: str):
            return []

        wrapped = retrieval("vector-search", search)
        wrapped("dogs")
        span = _last_span(fake_tracer)
        assert span.name == "vector-search"
        assert span.attributes["span.type"] == "retriever"

    def test_bare_decorator_uses_function_name(self, fake_tracer):
        @retrieval
        def semantic_search(query: str):
            return []

        semantic_search("test")
        span = _last_span(fake_tracer)
        assert span.name == "semantic_search"
        assert span.attributes["span.type"] == "retriever"

    def test_input_and_output_captured(self, fake_tracer):
        @retrieval("vector-search")
        def search(query: str):
            return ["doc1", "doc2"]

        search("cats")
        span = _last_span(fake_tracer)
        assert json.loads(span.attributes["input.value"]) == "cats"
        assert json.loads(span.attributes["output.value"]) == ["doc1", "doc2"]

    async def test_async_wrapper_call(self, fake_tracer):
        async def search(query: str):
            return [query]

        wrapped = retrieval("async-search", search)
        assert await wrapped("x") == ["x"]
        span = _last_span(fake_tracer)
        assert span.name == "async-search"
        assert span.attributes["span.type"] == "retriever"


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
