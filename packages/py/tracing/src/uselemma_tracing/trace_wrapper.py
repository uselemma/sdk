from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from opentelemetry import context, trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, StatusCode
from .experiment_mode import is_experiment_mode_enabled

T = TypeVar("T")
Input = TypeVar("Input")


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
            return False
        self._root_ended = True
        self.span.end()
        return True

    def record_error(self, error: Any) -> None:
        """Record an error on the span. Marks the span as errored."""
        exc = error if isinstance(error, BaseException) else Exception(str(error))
        self.span.record_exception(exc)
        self.span.set_status(StatusCode.ERROR)


def wrap_agent(
    agent_name: str,
    fn: Callable[[TraceContext, Input], T],
    *,
    is_experiment: bool = False,
    auto_end_root: bool = True,
) -> Callable[[Input], tuple[T, str, Span]]:
    """Wrap an agent function with OpenTelemetry tracing.

    Creates a new span on every invocation, attaches agent metadata
    (run ID, experiment flag), and handles error recording.

    Args:
        agent_name: Human-readable name used as the span name.
        fn: The agent function to wrap. Receives a :class:`TraceContext`
            as its first argument and the call-time ``input`` as its second.
        is_experiment: Mark this run as an experiment in Lemma.
        auto_end_root: Automatically end the top-level span when the wrapped
            function returns or throws (default: ``True``).  Set to ``False``
            to manage span lifetime manually via :meth:`TraceContext.on_complete`.

    Returns:
        A wrapper that accepts an ``input``, calls *fn* inside a traced
        context, and returns ``(result, run_id, span)``.

    Example::

        from typing import TypedDict

        class AgentInput(TypedDict):
            topic: str

        async def handler(ctx: TraceContext, input: AgentInput) -> str:
            result = await do_work(input["topic"])
            return result

        my_agent = wrap_agent("my-agent", handler)
        await my_agent({"topic": "math"})
    """

    def _start_root_span(input: Input) -> tuple[Span, str]:
        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())

        span = tracer.start_span(
            "ai.agent.run",
            context=Context(),
            attributes={
                "ai.agent.name": agent_name,
                "lemma.run_id": run_id,
                "lemma.is_experiment": is_experiment_mode_enabled() or is_experiment,
                "lemma.auto_end_root": auto_end_root,
            },
        )
        return span, run_id

    async def _wrapped_async(input: Input) -> tuple[T, str, Span]:
        import asyncio  # noqa: F811 – deferred so sync callers don't pay the import

        span, run_id = _start_root_span(input)

        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(
                span=span,
                run_id=run_id,
                auto_end_root=auto_end_root,
            )

            if asyncio.iscoroutinefunction(fn):
                result = await fn(trace_ctx, input)
            else:
                result = fn(trace_ctx, input)  # pragma: no cover

            if auto_end_root and not trace_ctx._root_ended:
                trace_ctx._root_ended = True
                span.end()

            return result, run_id, span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if not trace_ctx._root_ended:
                trace_ctx._root_ended = True
                span.end()
            raise
        finally:
            context.detach(token)

    def _wrapped_sync(input: Input) -> tuple[T, str, Span]:
        span, run_id = _start_root_span(input)

        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(
                span=span,
                run_id=run_id,
                auto_end_root=auto_end_root,
            )
            result = fn(trace_ctx, input)

            if auto_end_root and not trace_ctx._root_ended:
                trace_ctx._root_ended = True
                span.end()

            return result, run_id, span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if not trace_ctx._root_ended:
                trace_ctx._root_ended = True
                span.end()
            raise
        finally:
            context.detach(token)

    import asyncio

    if asyncio.iscoroutinefunction(fn):
        return _wrapped_async  # type: ignore[return-value]
    return _wrapped_sync  # type: ignore[return-value]
