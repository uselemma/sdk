import { context, ROOT_CONTEXT, trace, Span } from "@opentelemetry/api";
import { v4 as uuidv4 } from "uuid";
import { isExperimentModeEnabled } from "./experiment-mode";

export type TraceContext = {
  /** The active OpenTelemetry span for this agent run. */
  span: Span;
  /** Unique identifier for this agent run. */
  runId: string;
  /** Signal that the agent completed successfully. Records the result and ends the span. */
  onComplete: (result: unknown) => void;
  /** Signal that the agent encountered an error. Records the exception and ends the span. */
  onError: (error: unknown) => void;
  /** Attach arbitrary generation results (e.g. model outputs) to the span. */
  recordGenerationResults: (results: Record<string, string>) => void;
};

/**
 * Wraps an agent function with OpenTelemetry tracing, automatically creating
 * a span for the agent run and providing a `TraceContext` to the wrapped function.
 *
 * The returned function creates a new root span on every invocation, attaches
 * agent metadata (name, run ID, input, experiment flag), and handles error recording.
 * The `input` passed to the returned function is recorded as the agent's initial
 * state on the span.
 *
 * @example
 * const myAgent = wrapAgent<{ topic: string }>(
 *   'my-agent',
 *   async (ctx, input) => {
 *     // use ctx.span, ctx.runId, ctx.onComplete, etc.
 *     const result = await doWork(input.topic);
 *     ctx.onComplete(result);
 *   },
 * );
 * await myAgent({ topic: 'math' });
 *
 * @example
 * // Keep the span open after the function exits
 * const longRunning = wrapAgent(
 *   'streaming-agent',
 *   async (ctx, input) => {
 *     // caller is responsible for calling ctx.onComplete / ctx.onError
 *   },
 *   { endOnExit: false },
 * );
 *
 * @param agentName - Human-readable agent name recorded as `ai.agent.name`.
 * @param fn - The agent function to wrap. Receives a {@link TraceContext} as its first argument and the call-time input as its second.
 * @param options - Configuration for the agent trace.
 * @param options.isExperiment - Mark this run as an experiment in Lemma.
 * @param options.endOnExit - Whether to auto-end the span when the function returns. Defaults to `true`.
 * @returns An async function that accepts an `input`, executes `fn` inside a traced context, and returns `{ result, runId, span }`.
 */
export function wrapAgent<Input = unknown>(agentName: string, fn: (traceContext: TraceContext, input: Input) => any, options?: { isExperiment?: boolean, endOnExit?: boolean }) {
  const wrappedFunction = async function (this: any, input: Input) {
    // Obtain the Lemma tracer from the global OTel provider
    const tracer = trace.getTracer("lemma");

    // Generate a unique run ID and open a new span for this agent invocation
    const runId = uuidv4();
    const span = tracer.startSpan("ai.agent.run", {
      attributes: {
        "ai.agent.name": agentName,
        "lemma.run_id": runId,
        "ai.agent.input": JSON.stringify(input),
        "lemma.is_experiment": isExperimentModeEnabled() || options?.isExperiment === true,
      },
    }, ROOT_CONTEXT);

    // Propagate the span as the active context so child spans are nested correctly
    const ctx = trace.setSpan(ROOT_CONTEXT, span);

    try {
      return await context.with(ctx, async () => {
        // Build the TraceContext callbacks that the agent function can use
        // to manually signal completion, errors, or record generation results

        const onComplete = (result: unknown) => {
          span.setAttribute("ai.agent.output", JSON.stringify(result));
          span.end();
        };

        const onError = (error: unknown) => {
          // Normalise non-Error values so OTel always receives an Error instance
          span.recordException(error instanceof Error ? error : new Error(String(error)));
          span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
          span.end();
        };

        const recordGenerationResults = (results: Record<string, string>) => {
          span.setAttribute("ai.agent.generation_results", JSON.stringify(results));
        };

        // Invoke the wrapped agent function with the trace context and call-time input
        const result = await fn.call(this, { span, runId, onComplete, onError, recordGenerationResults }, input);

        // Auto-end the span unless the caller opted out (e.g. for streaming)
        if (options?.endOnExit !== false) {
          span.end();
        }

        return { result, runId, span };
      });
    } catch (err) {
      // Record the exception on the span and mark it as errored
      span.recordException(err as Error);
      span.setStatus({ code: 2 }); // SpanStatusCode.ERROR

      if (options?.endOnExit !== false) {
        span.end();
      }

      throw err;
    }
  };

  return wrappedFunction;
}
