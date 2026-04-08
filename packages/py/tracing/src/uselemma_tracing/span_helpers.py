"""Child-span helpers for Lemma tracing.

These decorators wrap functions with a child span under the currently active
context. Unlike :func:`wrap_agent`, they do **not** create a new trace root —
they add a child span to whatever span is currently active.

Usage
-----
All helpers support two forms:

**Bare decorator** — uses the function name as the span name::

    @trace
    async def format_output(raw: str) -> str:
        return raw.strip()

**Named decorator** — explicit span name::

    @trace("format-output")
    async def format_output(raw: str) -> str:
        return raw.strip()

The typed helpers (``tool``, ``llm``, ``retrieval``) prefix the span name::

    @tool("lookup-order")       # span: tool.lookup-order
    async def lookup_order(order_id: str) -> dict: ...

    @llm("gpt-4o")              # span: llm.gpt-4o
    async def generate(prompt: str) -> str: ...

    @retrieval("vector-search") # span: retrieval.vector-search
    async def search(query: str) -> list: ...
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, TypeVar, Union

from opentelemetry import trace as otel_trace
from opentelemetry.trace import StatusCode

F = TypeVar("F", bound=Callable[..., Any])


def _make_span_wrapper(span_name: str, fn: F) -> F:
    """Return a wrapper that runs *fn* inside a child span named *span_name*."""
    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = otel_trace.get_tracer("lemma")
            with tracer.start_as_current_span(span_name) as span:
                try:
                    return await fn(*args, **kwargs)
                except BaseException as exc:
                    span.record_exception(exc)
                    span.set_status(StatusCode.ERROR)
                    raise

        return async_wrapper  # type: ignore[return-value]
    else:
        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = otel_trace.get_tracer("lemma")
            with tracer.start_as_current_span(span_name) as span:
                try:
                    return fn(*args, **kwargs)
                except BaseException as exc:
                    span.record_exception(exc)
                    span.set_status(StatusCode.ERROR)
                    raise

        return sync_wrapper  # type: ignore[return-value]


def _span_decorator(prefix: str) -> Callable[..., Any]:
    """Build a decorator factory for spans with an optional *prefix*."""

    def decorator(fn_or_name: Union[F, str, None] = None, *, name: str | None = None) -> Any:
        # @trace  (bare — no parentheses)
        if callable(fn_or_name):
            fn = fn_or_name
            span_name = f"{prefix}.{fn.__name__}" if prefix else fn.__name__
            return _make_span_wrapper(span_name, fn)

        # @trace("my-name") or @trace(name="my-name")
        explicit_name: str | None
        if isinstance(fn_or_name, str):
            explicit_name = fn_or_name
        else:
            explicit_name = name

        def inner(fn: F) -> F:
            if explicit_name:
                span_name = f"{prefix}.{explicit_name}" if prefix else explicit_name
            else:
                span_name = f"{prefix}.{fn.__name__}" if prefix else fn.__name__
            return _make_span_wrapper(span_name, fn)

        return inner

    return decorator


#: Wraps a function with a child span. Use as ``@trace`` or ``@trace("name")``.
trace = _span_decorator("")

#: Wraps a tool function with a ``tool.<name>`` child span.
#: Use as ``@tool`` or ``@tool("search")``.
tool = _span_decorator("tool")

#: Wraps an LLM call with an ``llm.<name>`` child span.
#: Use as ``@llm`` or ``@llm("gpt-4o")``.
llm = _span_decorator("llm")

#: Wraps a retrieval function with a ``retrieval.<name>`` child span.
#: Use as ``@retrieval`` or ``@retrieval("vector-search")``.
retrieval = _span_decorator("retrieval")
