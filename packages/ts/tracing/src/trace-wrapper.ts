import { context, ROOT_CONTEXT, trace, Span } from "@opentelemetry/api";
import { v4 as uuidv4 } from "uuid";
import { isExperimentModeEnabled } from "./experiment-mode";

export type TraceContext = {
  /** The active OpenTelemetry span for this agent run. */
  span: Span;
  /** Unique identifier for this agent run. */
  runId: string;
  /**
   * Signal the run is complete. When `autoEndRoot` is enabled (the default),
   * this is a no-op and returns `false` — the span is ended automatically.
   * When `autoEndRoot` is disabled, this ends the top-level span and returns `true`.
   */
  onComplete: (result: unknown) => boolean;
  /** Record an error on the span. Marks the span as errored. */
  recordError: (error: unknown) => void;
};

export type WrapAgentOptions = {
  /** Mark this run as an experiment in Lemma. */
  isExperiment?: boolean;
  /**
   * If `true` (the default), the top-level span is automatically ended when
   * the wrapped function returns or throws. Set to `false` to manage span
   * lifetime manually via `ctx.onComplete`.
   */
  autoEndRoot?: boolean;
};

/**
 * Wraps an agent function with OpenTelemetry tracing, automatically creating
 * a span for the agent run and providing a `TraceContext` to the wrapped function.
 *
 * The returned function creates a new root span on every invocation, attaches
 * agent metadata (name, run ID, experiment flag), and handles error recording.
 *
 * @example
 * const myAgent = wrapAgent<{ topic: string }>(
 *   'my-agent',
 *   async (ctx, input) => {
 *     const result = await doWork(input.topic);
 *     ctx.onComplete(result);
 *   },
 * );
 * await myAgent({ topic: 'math' });
 *
 * @param agentName - Human-readable agent name recorded as `ai.agent.name`.
 * @param fn - The agent function to wrap. Receives a {@link TraceContext} as its first argument and the call-time input as its second.
 * @param options - Configuration for the agent trace.
 * @param options.isExperiment - Mark this run as an experiment in Lemma.
 * @param options.autoEndRoot - Automatically end the top-level span when the wrapped function returns or throws (default: `true`). Set to `false` to end manually via `ctx.onComplete`.
 * @returns An async function that accepts an `input`, executes `fn` inside a traced context, and returns `{ result, runId, span }`.
 */
export function wrapAgent<Input = unknown>(agentName: string, fn: (traceContext: TraceContext, input: Input) => any, options?: WrapAgentOptions) {
  const wrappedFunction = async function (this: any, input: Input) {
    // Obtain the Lemma tracer from the global OTel provider
    const tracer = trace.getTracer("lemma");

    // Generate a unique run ID and open a new span for this agent invocation
    const runId = uuidv4();
    const autoEndRoot = options?.autoEndRoot !== false; // default true
    const span = tracer.startSpan("ai.agent.run", {
      attributes: {
        "ai.agent.name": agentName,
        "lemma.run_id": runId,
        "lemma.is_experiment": isExperimentModeEnabled() || options?.isExperiment === true,
        "lemma.auto_end_root": autoEndRoot,
      },
    }, ROOT_CONTEXT);

    // Propagate the span as the active context so child spans are nested correctly
    const ctx = trace.setSpan(ROOT_CONTEXT, span);
    let rootEnded = false;

    try {
      return await context.with(ctx, async () => {
        const onComplete = (_result: unknown): boolean => {
          if (!autoEndRoot && !rootEnded) {
            rootEnded = true;
            span.end();
            return true;
          }
          return false;
        };

        const recordError = (error: unknown) => {
          span.recordException(error instanceof Error ? error : new Error(String(error)));
          span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
        };

        const result = await fn.call(this, { span, runId, onComplete, recordError }, input);

        // Auto-end the span if autoEndRoot is enabled and onComplete hasn't ended it yet
        if (autoEndRoot && !rootEnded) {
          rootEnded = true;
          span.end();
        }

        return { result, runId, span };
      });
    } catch (err) {
      // Record the exception on the span, mark it as errored, and end it
      span.recordException(err as Error);
      span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
      if (!rootEnded) {
        rootEnded = true;
        span.end();
      }

      throw err;
    }
  };

  return wrappedFunction;
}
