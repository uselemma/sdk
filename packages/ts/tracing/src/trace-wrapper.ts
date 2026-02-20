import { context, ROOT_CONTEXT, trace, Span } from "@opentelemetry/api";
import { v4 as uuidv4 } from "uuid";
import { isExperimentModeEnabled } from "./experiment-mode";

export type TraceContext = {
  /** The active OpenTelemetry span for this agent run. */
  span: Span;
  /** Unique identifier for this agent run. */
  runId: string;
  /**
   * Record output and complete the run when `autoEndRoot` is disabled.
   * Returns `true` when this call ends the top-level span.
   */
  complete: (result: unknown) => boolean;
  /** Record an error on the span. Marks the span as errored. */
  recordError: (error: unknown) => void;
};

export type WrapAgentOptions = {
  /** Mark this run as an experiment in Lemma. */
  isExperiment?: boolean;
  /**
   * If `true`, the run processor will automatically end the top-level span
   * when all direct child spans have ended.
   */
  autoEndRoot?: boolean;
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
 *     const result = await doWork(input.topic);
 *     ctx.complete(result);
 *   },
 * );
 * await myAgent({ topic: 'math' });
 *
 * @param agentName - Human-readable agent name recorded as `ai.agent.name`.
 * @param fn - The agent function to wrap. Receives a {@link TraceContext} as its first argument and the call-time input as its second.
 * @param options - Configuration for the agent trace.
 * @param options.isExperiment - Mark this run as an experiment in Lemma.
 * @param options.autoEndRoot - Enable processor-driven automatic ending of the top-level span after direct children have ended.
 * @returns An async function that accepts an `input`, executes `fn` inside a traced context, and returns `{ result, runId, span }`.
 */
export function wrapAgent<Input = unknown>(agentName: string, fn: (traceContext: TraceContext, input: Input) => any, options?: WrapAgentOptions) {
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
        "lemma.auto_end_root": options?.autoEndRoot === true,
      },
    }, ROOT_CONTEXT);

    // Propagate the span as the active context so child spans are nested correctly
    const ctx = trace.setSpan(ROOT_CONTEXT, span);
    const autoEndRoot = options?.autoEndRoot === true;
    let rootEnded = false;

    try {
      return await context.with(ctx, async () => {
        const complete = (result: unknown): boolean => {
          span.setAttribute("ai.agent.output", JSON.stringify(result));
          if (autoEndRoot || rootEnded) return false;
          rootEnded = true;
          span.end();
          return true;
        };

        const recordError = (error: unknown) => {
          span.recordException(error instanceof Error ? error : new Error(String(error)));
          span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
        };

        const result = await fn.call(this, { span, runId, complete, recordError }, input);

        return { result, runId, span };
      });
    } catch (err) {
      // Record the exception on the span and mark it as errored
      span.recordException(err as Error);
      span.setStatus({ code: 2 }); // SpanStatusCode.ERROR

      throw err;
    }
  };

  return wrappedFunction;
}
