from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from opentelemetry import context, trace
from opentelemetry.trace import Span, StatusCode

T = TypeVar("T")


@dataclass
class TraceContext:
    """Context object passed to the wrapped agent function."""

    span: Span
    """The active OpenTelemetry span for this agent run."""

    run_id: str
    """Unique identifier for this agent run."""

    _ended: bool = field(default=False, init=False, repr=False)

    def on_complete(self, result: Any) -> None:
        """Signal successful completion. Records the result and ends the span."""
        self.span.set_attribute("lemma.agent.output", json.dumps(result, default=str))
        self.span.end()
        self._ended = True

    def on_error(self, error: Any) -> None:
        """Signal an error. Records the exception and ends the span."""
        exc = error if isinstance(error, BaseException) else Exception(str(error))
        self.span.record_exception(exc)
        self.span.set_status(StatusCode.ERROR)
        self.span.end()
        self._ended = True

    def record_generation_results(self, results: dict[str, str]) -> None:
        """Attach arbitrary generation results to the span."""
        self.span.set_attribute("lemma.agent.generation_results", json.dumps(results, default=str))


def wrap_agent(
    agent_name: str,
    fn: Callable[..., T],
    *,
    initial_state: Any = None,
    is_experiment: bool = False,
    end_on_exit: bool = True,
) -> Callable[..., tuple[T, str, Span]]:
    """Wrap an agent function with OpenTelemetry tracing.

    Creates a new span on every invocation, attaches agent metadata
    (run ID, input, experiment flag), and handles error recording.

    Args:
        agent_name: Human-readable name used as the span name.
        fn: The agent function to wrap. Receives a :class:`TraceContext`
            as its first argument.
        initial_state: Arbitrary state serialised as the agent input attribute.
        is_experiment: Mark this run as an experiment in Lemma.
        end_on_exit: Whether to auto-end the span when the function returns.
            Defaults to ``True``.

    Returns:
        A wrapper that calls *fn* inside a traced context and returns
        ``(result, run_id, span)``.
    """

    async def _wrapped_async(*args: Any, **kwargs: Any) -> tuple[T, str, Span]:
        import asyncio  # noqa: F811 – deferred so sync callers don't pay the import

        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())

        span = tracer.start_span(
            agent_name,
            attributes={
                "lemma.agent.run_id": run_id,
                "lemma.agent.input": json.dumps(initial_state, default=str),
                "lemma.agent.is_experiment": is_experiment,
            },
        )

        ctx = trace.set_span_in_context(span)
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id)

            if asyncio.iscoroutinefunction(fn):
                result = await fn(trace_ctx, *args, **kwargs)
            else:
                result = fn(trace_ctx, *args, **kwargs)

            if end_on_exit and not trace_ctx._ended:
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

    def _wrapped_sync(*args: Any, **kwargs: Any) -> tuple[T, str, Span]:
        tracer = trace.get_tracer("lemma")
        run_id = str(uuid.uuid4())

        span = tracer.start_span(
            agent_name,
            attributes={
                "lemma.agent.run_id": run_id,
                "lemma.agent.input": json.dumps(initial_state, default=str),
                "lemma.agent.is_experiment": is_experiment,
            },
        )

        ctx = trace.set_span_in_context(span)
        token = context.attach(ctx)

        try:
            trace_ctx = TraceContext(span=span, run_id=run_id)
            result = fn(trace_ctx, *args, **kwargs)

            if end_on_exit and not trace_ctx._ended:
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
