from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
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

    def on_complete(self, result: Any) -> None:
        """Signal successful completion. Records the result on the span."""
        self.span.set_attribute("ai.agent.output", json.dumps(result, default=str))

    def on_error(self, error: Any) -> None:
        """Signal an error. Records the exception on the span."""
        exc = error if isinstance(error, BaseException) else Exception(str(error))
        self.span.record_exception(exc)
        self.span.set_status(StatusCode.ERROR)

    def record_generation_results(self, results: dict[str, str]) -> None:
        """Attach arbitrary generation results to the span."""
        self.span.set_attribute(
            "ai.agent.generation_results", json.dumps(results, default=str)
        )


def wrap_agent(
    agent_name: str,
    fn: Callable[[TraceContext, Input], T],
    *,
    is_experiment: bool = False,
    end_on_exit: bool = True,
) -> Callable[[Input], tuple[T, str, Span]]:
    """Wrap an agent function with OpenTelemetry tracing.

    Creates a new span on every invocation, attaches agent metadata
    (run ID, input, experiment flag), and handles error recording.
    The ``input`` passed to the returned function is recorded as the
    agent's initial state on the span.

    Args:
        agent_name: Human-readable name used as the span name.
        fn: The agent function to wrap. Receives a :class:`TraceContext`
            as its first argument and the call-time ``input`` as its second.
        is_experiment: Mark this run as an experiment in Lemma.
        end_on_exit: Whether to auto-end the span when the function returns.
            Defaults to ``True``.

    Returns:
        A wrapper that accepts an ``input``, calls *fn* inside a traced
        context, and returns ``(result, run_id, span)``.

    Example::

        from typing import TypedDict

        class AgentInput(TypedDict):
            topic: str

        async def handler(ctx: TraceContext, input: AgentInput) -> str:
            result = await do_work(input["topic"])
            ctx.on_complete(result)
            return result

        my_agent = wrap_agent("my-agent", handler)
        await my_agent({"topic": "math"})
    """

    async def _wrapped_async(input: Input) -> tuple[T, str, Span]:
        import asyncio  # noqa: F811 – deferred so sync callers don't pay the import

        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())

        span = tracer.start_span(
            "ai.agent.run",
            context=Context(),
            attributes={
                "ai.agent.name": agent_name,
                "lemma.run_id": run_id,
                "ai.agent.input": json.dumps(input, default=str),
                "lemma.is_experiment": is_experiment_mode_enabled() or is_experiment,
            },
        )

        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id)

            if asyncio.iscoroutinefunction(fn):
                result = await fn(trace_ctx, input)
            else:
                result = fn(trace_ctx, input)

            if end_on_exit:
                span.end()

            return result, run_id, span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if end_on_exit:
                span.end()
            raise
        finally:
            context.detach(token)

    def _wrapped_sync(input: Input) -> tuple[T, str, Span]:
        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())

        span = tracer.start_span(
            "ai.agent.run",
            context=Context(),
            attributes={
                "ai.agent.name": agent_name,
                "lemma.run_id": run_id,
                "ai.agent.input": json.dumps(input, default=str),
                "lemma.is_experiment": is_experiment_mode_enabled() or is_experiment,
            },
        )

        ctx = trace.set_span_in_context(span, Context())
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id)
            result = fn(trace_ctx, input)

            if end_on_exit:
                span.end()

            return result, run_id, span
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR)
            if end_on_exit:
                span.end()
            raise
        finally:
            context.detach(token)

    import asyncio

    if asyncio.iscoroutinefunction(fn):
        return _wrapped_async  # type: ignore[return-value]
    return _wrapped_sync  # type: ignore[return-value]
