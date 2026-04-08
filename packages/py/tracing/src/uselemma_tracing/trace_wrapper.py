from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Mapping, TypeVar, overload

from opentelemetry import context, trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, StatusCode
from .debug_mode import _lemma_debug
from .experiment_mode import is_experiment_mode_enabled

T = TypeVar("T")
Input = TypeVar("Input")


def _normalize_thread_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


@dataclass
class TraceResult(Generic[T]):
    """Named return type from :func:`agent`.

    Supports both attribute access and tuple unpacking for backward
    compatibility::

        # Named access (recommended)
        res = await wrapped(input)
        print(res.result, res.run_id)

        # Tuple unpacking (backward compatible)
        result, run_id, span = await wrapped(input)
    """

    result: T
    """The value returned by the wrapped agent function."""

    run_id: str
    """Unique identifier for this agent run. Use it to link metric events."""

    span: Span
    """The underlying OpenTelemetry span for this run."""

    def __iter__(self):  # type: ignore[override]
        return iter((self.result, self.run_id, self.span))

    def __getitem__(self, index: int) -> Any:
        return (self.result, self.run_id, self.span)[index]


def _resolve_is_experiment(
    run_options: Mapping[str, Any] | None,
    default_is_experiment: bool,
) -> bool:
    if is_experiment_mode_enabled():
        return True
    if run_options is not None and "is_experiment" in run_options:
        run_is_experiment = run_options.get("is_experiment")
        if run_is_experiment is not None:
            return bool(run_is_experiment)
    return default_is_experiment


@dataclass
class TraceContext:
    """Context object passed to the wrapped agent function."""

    span: Span
    """The active OpenTelemetry span for this agent run."""

    run_id: str
    """Unique identifier for this agent run."""

    _root_ended: bool = field(default=False, init=False, repr=False)

    def complete(self, result: Any = None) -> None:
        """Override the run output and close the span immediately.

        In non-streaming agents, ``complete()`` is **optional** — the wrapper
        automatically captures the return value as ``ai.agent.output`` and
        closes the span when the function returns. Call it explicitly only
        when you need to record a different output than the return value, or
        close the span before the function exits.

        In streaming agents (``streaming=True``), ``complete()`` is
        **required** — call it inside the stream's finish callback once the
        full output is assembled.

        Idempotent: the first call wins, subsequent calls are no-ops.
        """
        if self._root_ended:
            return
        self.span.set_attribute("ai.agent.output", json.dumps(result, default=str))
        self._root_ended = True
        self.span.end()
        _lemma_debug("trace-wrapper", "complete called", run_id=self.run_id)

    def on_complete(self, result: Any) -> None:
        """Deprecated. Use :meth:`complete` instead."""
        self.complete(result)

    def fail(self, error: Any) -> None:
        """Record an error on the span and mark the run as failed.

        Does not close the span — the wrapper handles closing on return or error.
        """
        exc = error if isinstance(error, BaseException) else Exception(str(error))
        self.span.record_exception(exc)
        self.span.set_status(StatusCode.ERROR)

    def record_error(self, error: Any) -> None:
        """Deprecated. Use :meth:`fail` instead."""
        self.fail(error)


@dataclass
class RunContext:
    """Context object yielded by :func:`agent` when used as a context manager.

    The span ends when the ``with`` / ``async with`` block exits.
    Call :meth:`complete` to set the run output; the span itself is closed
    by the context manager on scope exit.
    """

    span: Span
    """The active OpenTelemetry span for this agent run."""

    run_id: str
    """Unique identifier for this agent run."""

    _ended: bool = field(default=False, init=False, repr=False)

    def complete(self, result: Any = None) -> None:
        """Record the run output.

        Sets ``ai.agent.output`` on the span. The span itself is ended by the
        context manager when the ``with`` block exits, not by this call.
        """
        self.span.set_attribute("ai.agent.output", json.dumps(result, default=str))
        _lemma_debug("trace-wrapper", "complete called (context manager)", run_id=self.run_id)

    def on_complete(self, result: Any) -> None:
        """Deprecated. Use :meth:`complete` instead."""
        self.complete(result)

    def fail(self, error: Any) -> None:
        """Record an error on the span and mark the run as failed."""
        exc = error if isinstance(error, BaseException) else Exception(str(error))
        self.span.record_exception(exc)
        self.span.set_status(StatusCode.ERROR)

    def record_error(self, error: Any) -> None:
        """Deprecated. Use :meth:`fail` instead."""
        self.fail(error)


class _WrapAgentContextManager:
    """Internal context manager returned by agent when called without fn."""

    def __init__(
        self,
        agent_name: str,
        *,
        input: Any = None,
        is_experiment: bool = False,
    ) -> None:
        self._agent_name = agent_name
        self._input = input
        self._is_experiment = is_experiment
        self._token: object | None = None
        self._run: RunContext | None = None

    def _start(self) -> RunContext:
        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())

        span = tracer.start_span(
            "ai.agent.run",
            context=Context(),
            attributes={
                "ai.agent.name": self._agent_name,
                "lemma.run_id": run_id,
                "lemma.is_experiment": is_experiment_mode_enabled() or self._is_experiment,
            },
        )
        span.set_attribute("ai.agent.input", json.dumps(self._input, default=str))
        _lemma_debug("trace-wrapper", "span started (context manager)", agent_name=self._agent_name, run_id=run_id)

        ctx = trace.set_span_in_context(span, Context())
        self._token = context.attach(ctx)
        self._run = RunContext(span=span, run_id=run_id)
        return self._run

    def _end(self, exc_val: BaseException | None) -> None:
        run = self._run
        if run is None:
            return

        if exc_val is not None:
            run.fail(exc_val)

        if not run._ended:
            run._ended = True
            run.span.end()
            _lemma_debug("trace-wrapper", "span ended (context manager exit)", run_id=run.run_id)

        if self._token is not None:
            context.detach(self._token)
            self._token = None

    def __enter__(self) -> RunContext:
        return self._start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        self._end(exc_val)
        return False

    async def __aenter__(self) -> RunContext:
        return self._start()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        self._end(exc_val)
        return False


# ---------------------------------------------------------------------------
# Overload signatures — used by type checkers only, not at runtime.
# ---------------------------------------------------------------------------

@overload
def agent(
    agent_name: str,
    fn: Callable[[TraceContext, Input], T],
    *,
    is_experiment: bool = ...,
    streaming: bool = ...,
) -> Callable[[Input, Mapping[str, Any] | None], TraceResult[T]]: ...


@overload
def agent(
    agent_name: str,
    *,
    input: Any = ...,
    is_experiment: bool = ...,
) -> _WrapAgentContextManager: ...


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

def agent(
    agent_name: str,
    fn: Callable[[TraceContext, Input], T] | None = None,
    *,
    input: Any = None,
    is_experiment: bool = False,
    streaming: bool = False,
) -> Callable[[Input, Mapping[str, Any] | None], TraceResult[T]] | _WrapAgentContextManager:
    """Wrap an agent function with OpenTelemetry tracing, or open a traced context block.

    **Callable wrapper** (pass ``fn``): returns a traced version of your function.

    For **non-streaming** agents (default), simply return a value — the wrapper
    captures it as ``ai.agent.output`` and closes the span automatically. No call
    to ``ctx.complete()`` is required.

    For **streaming** agents, pass ``streaming=True``. The wrapper will not
    auto-close the span on return. Call :meth:`TraceContext.complete` inside
    the stream's finish callback once the full output is assembled.

    **Context manager** (omit ``fn``): returns a context manager that opens a run
    span for the duration of the ``with`` / ``async with`` block — no function
    extraction needed. The span ends on scope exit; call :meth:`RunContext.complete`
    to set the output.

    Args:
        agent_name: Human-readable name recorded as ``ai.agent.name``.
        fn: The agent function to wrap. When provided, ``agent`` returns a callable
            wrapper. When omitted, it returns a context manager.
        input: Run input (context manager mode only). Serialized as ``ai.agent.input``.
        is_experiment: Mark this run as an experiment in Lemma.
        streaming: When ``True``, disables auto-close on return. The wrapped
            function must call ``ctx.complete(output)`` before the span is exported.

    Returns:
        A callable wrapper ``(input, options=None) -> TraceResult[T]`` when ``fn`` is
        provided, or a context manager yielding a :class:`RunContext` when ``fn`` is omitted.

    Examples::

        # Non-streaming — just return a value
        async def run_agent(user_message: str, ctx: TraceContext) -> str:
            result = await call_llm(user_message)
            return result  # wrapper auto-captures output and closes the span

        wrapped = agent("my-agent", run_agent)
        res = await wrapped(user_message)
        print(res.result, res.run_id)

        # Streaming — opt into manual lifecycle
        async def streaming_agent(user_message: str, ctx: TraceContext):
            stream = create_stream(user_message)
            stream.on_finish(ctx.complete)  # close span when stream finishes
            return stream

        wrapped_streaming = agent("streaming-agent", streaming_agent, streaming=True)

        # Context manager — instrument in-place, no refactor needed
        async with agent("my-agent", input=user_message) as run:
            result = await call_llm(user_message)
            run.complete(result)

        print(run.run_id)
    """
    if fn is None:
        return _WrapAgentContextManager(agent_name, input=input, is_experiment=is_experiment)

    def _start_root_span(
        agent_input: Input, run_options: Mapping[str, Any] | None = None
    ) -> tuple[Span, str]:
        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())
        thread_id = _normalize_thread_id(
            run_options.get("thread_id") if run_options is not None else None
        )
        attributes: dict[str, Any] = {
            "ai.agent.name": agent_name,
            "lemma.run_id": run_id,
            "lemma.is_experiment": _resolve_is_experiment(
                run_options, is_experiment
            ),
        }
        if thread_id is not None:
            attributes["lemma.thread_id"] = thread_id

        span = tracer.start_span(
            "ai.agent.run",
            context=Context(),
            attributes=attributes,
        )
        span.set_attribute("ai.agent.input", json.dumps(agent_input, default=str))
        _lemma_debug("trace-wrapper", "span started", agent_name=agent_name, run_id=run_id)
        return span, run_id

    async def _wrapped_async(
        agent_input: Input, run_options: Mapping[str, Any] | None = None
    ) -> TraceResult[T]:
        import asyncio

        span, run_id = _start_root_span(agent_input, run_options)
        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)
        trace_ctx: TraceContext | None = None

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id)

            if asyncio.iscoroutinefunction(fn):
                result = await fn(agent_input, trace_ctx)
            else:
                result = fn(agent_input, trace_ctx)  # pragma: no cover

            if not streaming and not trace_ctx._root_ended:
                trace_ctx.complete(result)
            elif streaming and not trace_ctx._root_ended:
                _lemma_debug(
                    "trace-wrapper",
                    "streaming agent returned without complete()",
                    agent_name=agent_name,
                    run_id=run_id,
                )
                import warnings
                warnings.warn(
                    f"[lemma] Streaming agent '{agent_name}' returned without calling "
                    f"ctx.complete(). Call ctx.complete(output) inside the stream's "
                    f"finish callback to close the run span.",
                    stacklevel=2,
                )

            return TraceResult(result=result, run_id=run_id, span=span)
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if trace_ctx is None or not trace_ctx._root_ended:
                if trace_ctx is not None:
                    trace_ctx._root_ended = True
                span.end()
                _lemma_debug("trace-wrapper", "span ended on error", run_id=run_id, error=str(exc))
            raise
        finally:
            context.detach(token)

    def _wrapped_sync(
        agent_input: Input, run_options: Mapping[str, Any] | None = None
    ) -> TraceResult[T]:
        span, run_id = _start_root_span(agent_input, run_options)
        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)
        trace_ctx: TraceContext | None = None

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id)
            result = fn(agent_input, trace_ctx)

            if not streaming and not trace_ctx._root_ended:
                trace_ctx.complete(result)
            elif streaming and not trace_ctx._root_ended:
                _lemma_debug(
                    "trace-wrapper",
                    "streaming agent returned without complete()",
                    agent_name=agent_name,
                    run_id=run_id,
                )
                import warnings
                warnings.warn(
                    f"[lemma] Streaming agent '{agent_name}' returned without calling "
                    f"ctx.complete(). Call ctx.complete(output) inside the stream's "
                    f"finish callback to close the run span.",
                    stacklevel=2,
                )

            return TraceResult(result=result, run_id=run_id, span=span)
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if trace_ctx is None or not trace_ctx._root_ended:
                if trace_ctx is not None:
                    trace_ctx._root_ended = True
                span.end()
                _lemma_debug("trace-wrapper", "span ended on error", run_id=run_id, error=str(exc))
            raise
        finally:
            context.detach(token)

    import asyncio

    if asyncio.iscoroutinefunction(fn):
        return _wrapped_async  # type: ignore[return-value]
    return _wrapped_sync  # type: ignore[return-value]


def wrap_agent(
    agent_name: str,
    fn: Callable[[TraceContext, Input], T] | None = None,
    *,
    input: Any = None,
    is_experiment: bool = False,
) -> Callable[[Input, Mapping[str, Any] | None], TraceResult[T]] | _WrapAgentContextManager:
    """Deprecated. Use :func:`agent` instead.

    ``wrap_agent`` will be removed in a future major version.
    """
    import warnings

    warnings.warn(
        "wrap_agent() is deprecated — use agent() instead. "
        "wrap_agent will be removed in a future major version.",
        DeprecationWarning,
        stacklevel=2,
    )
    return agent(agent_name, fn, input=input, is_experiment=is_experiment)  # type: ignore[return-value]


# Backward-compatible alias exported for users who adopted the 2.12.0 / 2.13.0 API.
lemma_run = _WrapAgentContextManager
