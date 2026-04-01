from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, overload

from opentelemetry import context, trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, StatusCode
from .debug_mode import _lemma_debug
from .experiment_mode import is_experiment_mode_enabled

T = TypeVar("T")
Input = TypeVar("Input")

# Sentinel for detecting whether auto_end_root was explicitly passed.
_UNSET: Any = object()


@dataclass
class TraceContext:
    """Context object passed to the wrapped agent function."""

    span: Span
    """The active OpenTelemetry span for this agent run."""

    run_id: str
    """Unique identifier for this agent run."""
    auto_end_root: bool = True
    _root_ended: bool = field(default=False, init=False, repr=False)

    def on_complete(self, result: Any) -> bool:
        """Signal the run is complete.

        When ``auto_end_root`` is enabled (the default), this is a no-op and
        returns ``False`` — the span is ended automatically when the wrapped
        function returns.  When ``auto_end_root`` is disabled, this ends the
        top-level span and returns ``True``.
        """
        if self.auto_end_root or self._root_ended:
            _lemma_debug("trace-wrapper", "on_complete called but span not ended (auto_end_root active or already ended)", run_id=self.run_id)
            return False
        self.span.set_attribute("ai.agent.output", json.dumps(result, default=str))
        self._root_ended = True
        self.span.end()
        _lemma_debug("trace-wrapper", "span ended via on_complete", run_id=self.run_id)
        return True

    def record_error(self, error: Any) -> None:
        """Record an error on the span. Marks the span as errored."""
        exc = error if isinstance(error, BaseException) else Exception(str(error))
        self.span.record_exception(exc)
        self.span.set_status(StatusCode.ERROR)


@dataclass
class RunContext:
    """Context object yielded by :func:`wrap_agent` when used as a context manager.

    Unlike :class:`TraceContext`, there is no ``auto_end_root`` concept — the span
    always ends when the ``with`` / ``async with`` block exits.
    """

    span: Span
    """The active OpenTelemetry span for this agent run."""

    run_id: str
    """Unique identifier for this agent run."""

    _ended: bool = field(default=False, init=False, repr=False)

    def on_complete(self, result: Any) -> None:
        """Record the run output.

        Sets ``ai.agent.output`` on the span. The span itself is ended by the
        context manager when the ``with`` block exits, not by this call.
        """
        self.span.set_attribute("ai.agent.output", json.dumps(result, default=str))
        _lemma_debug("trace-wrapper", "on_complete called (context manager)", run_id=self.run_id)

    def record_error(self, error: Any) -> None:
        """Record an error on the span. Marks the span as errored."""
        exc = error if isinstance(error, BaseException) else Exception(str(error))
        self.span.record_exception(exc)
        self.span.set_status(StatusCode.ERROR)


class _WrapAgentContextManager:
    """Internal context manager returned by wrap_agent when called without fn."""

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
                "lemma.auto_end_root": False,
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
            run.record_error(exc_val)

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


# Backward-compatible alias exported for users who adopted the 2.12.0 API.
lemma_run = _WrapAgentContextManager


# ---------------------------------------------------------------------------
# Overload signatures — used by type checkers only, not at runtime.
# ---------------------------------------------------------------------------

@overload
def wrap_agent(
    agent_name: str,
    fn: Callable[[TraceContext, Input], T],
    *,
    is_experiment: bool = ...,
    auto_end_root: bool = ...,
) -> Callable[[Input], tuple[T, str, Span]]: ...


@overload
def wrap_agent(
    agent_name: str,
    *,
    input: Any = ...,
    is_experiment: bool = ...,
) -> _WrapAgentContextManager: ...


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

def wrap_agent(
    agent_name: str,
    fn: Callable[[TraceContext, Input], T] | None = None,
    *,
    input: Any = None,
    is_experiment: bool = False,
    auto_end_root: Any = _UNSET,
) -> Callable[[Input], tuple[T, str, Span]] | _WrapAgentContextManager:
    """Wrap an agent function with OpenTelemetry tracing, or open a traced context block.

    **Callable wrapper** (pass ``fn``): returns a traced version of your function.

    **Context manager** (omit ``fn``): returns a context manager that opens a run span
    for the duration of the ``with`` / ``async with`` block — no function extraction needed.

    Args:
        agent_name: Human-readable name recorded as ``ai.agent.name``.
        fn: The agent function to wrap. When provided, ``wrap_agent`` returns a callable
            wrapper. When omitted, it returns a context manager.
        input: Run input (context manager mode only). Serialized as ``ai.agent.input``.
        is_experiment: Mark this run as an experiment in Lemma.
        auto_end_root: Callable mode only. If ``True`` (default), the root span ends
            automatically when the wrapped function returns or throws. Set to ``False``
            to end it manually via :meth:`TraceContext.on_complete`.

    Returns:
        A callable wrapper ``(input) -> (result, run_id, span)`` when ``fn`` is provided,
        or a context manager yielding a :class:`RunContext` when ``fn`` is omitted.

    Examples::

        # Callable wrapper
        async def run_agent(ctx: TraceContext, user_message: str) -> str:
            result = await call_llm(user_message)
            ctx.on_complete(result)
            return result

        wrapped = wrap_agent("my-agent", run_agent)
        result, run_id, _ = await wrapped(user_message)

        # Context manager — instrument in-place, no refactor needed
        async with wrap_agent("my-agent", input=user_message) as run:
            result = await call_llm(user_message)
            run.on_complete(result)

        print(run.run_id)
    """
    # ---- context manager path ----
    if fn is None:
        if auto_end_root is not _UNSET:
            raise TypeError(
                "auto_end_root is not supported when using wrap_agent as a context manager "
                "(the span always ends when the with block exits). "
                "Remove the auto_end_root argument, or pass a function as the second argument "
                "to use wrap_agent as a callable wrapper."
            )
        return _WrapAgentContextManager(agent_name, input=input, is_experiment=is_experiment)

    # ---- callable wrapper path ----
    _auto_end_root: bool = True if auto_end_root is _UNSET else auto_end_root

    def _start_root_span(agent_input: Input) -> tuple[Span, str]:
        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())

        span = tracer.start_span(
            "ai.agent.run",
            context=Context(),
            attributes={
                "ai.agent.name": agent_name,
                "lemma.run_id": run_id,
                "lemma.is_experiment": is_experiment_mode_enabled() or is_experiment,
                "lemma.auto_end_root": _auto_end_root,
            },
        )
        span.set_attribute("ai.agent.input", json.dumps(agent_input, default=str))
        _lemma_debug("trace-wrapper", "span started", agent_name=agent_name, run_id=run_id, auto_end_root=_auto_end_root)
        return span, run_id

    async def _wrapped_async(agent_input: Input) -> tuple[T, str, Span]:
        import asyncio  # noqa: F811 – deferred so sync callers don't pay the import

        span, run_id = _start_root_span(agent_input)
        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id, auto_end_root=_auto_end_root)

            if asyncio.iscoroutinefunction(fn):
                result = await fn(trace_ctx, agent_input)
            else:
                result = fn(trace_ctx, agent_input)  # pragma: no cover

            if _auto_end_root and not trace_ctx._root_ended:
                span.set_attribute("ai.agent.output", json.dumps(result, default=str))
                trace_ctx._root_ended = True
                span.end()
                _lemma_debug("trace-wrapper", "span auto-ended after fn returned", run_id=run_id)

            return result, run_id, span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if not trace_ctx._root_ended:
                trace_ctx._root_ended = True
                span.end()
                _lemma_debug("trace-wrapper", "span ended on error", run_id=run_id, error=str(exc))
            raise
        finally:
            context.detach(token)

    def _wrapped_sync(agent_input: Input) -> tuple[T, str, Span]:
        span, run_id = _start_root_span(agent_input)
        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id, auto_end_root=_auto_end_root)
            result = fn(trace_ctx, agent_input)

            if _auto_end_root and not trace_ctx._root_ended:
                span.set_attribute("ai.agent.output", json.dumps(result, default=str))
                trace_ctx._root_ended = True
                span.end()
                _lemma_debug("trace-wrapper", "span auto-ended after fn returned", run_id=run_id)

            return result, run_id, span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if not trace_ctx._root_ended:
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
