import { context, ROOT_CONTEXT, trace, Span } from "@opentelemetry/api";
import { v4 as uuidv4 } from "uuid";
import { lemmaDebug } from "./debug-mode";
import { isExperimentModeEnabled } from "./experiment-mode";

export type TraceContext = {
  /** The active OpenTelemetry span for this agent run. */
  span: Span;
  /** Unique identifier for this agent run. */
  runId: string;
  /**
   * Record the run output and end the agent span. Sets `ai.agent.output` on
   * the span and calls `span.end()` — the parent span does not end until you
   * call this (except on uncaught errors, which still end the span).
   */
  onComplete: (result: unknown) => void;
  /** Record an error on the span. Marks the span as errored. */
  recordError: (error: unknown) => void;
};

export type WrapAgentOptions = {
  /** Mark this run as an experiment in Lemma. */
  isExperiment?: boolean;
};

export type WrapRunOptions = {
  /** Optional thread identifier for this invocation. */
  threadId?: string;
  /** Mark this specific invocation as an experiment. */
  isExperiment?: boolean;
};

function resolveIsExperiment(
  globalEnabled: boolean,
  wrapperOptions?: WrapAgentOptions,
  runOptions?: WrapRunOptions
): boolean {
  if (globalEnabled) return true;
  if (typeof runOptions?.isExperiment === "boolean") return runOptions.isExperiment;
  return wrapperOptions?.isExperiment === true;
}

function normalizeThreadId(threadId: unknown): string | undefined {
  if (typeof threadId !== "string") return undefined;
  const trimmed = threadId.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/**
 * Wraps an agent function with OpenTelemetry tracing, automatically creating
 * a span for the agent run and providing a `TraceContext` to the wrapped function.
 *
 * The returned function creates a new root span on every invocation, attaches
 * agent metadata (name, run ID, experiment flag), and handles error recording.
 *
 * `ai.agent.input` and `ai.agent.output` are set as JSON strings for Lemma
 * ingestion and UI. You must call {@link TraceContext.onComplete} to set
 * output and end the span. Uncaught errors still end the span with an error status.
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
 * @returns An async function that accepts an `input`, executes `fn` inside a traced context, and returns `{ result, runId, span }`.
 */
export function wrapAgent<Input = unknown>(
  agentName: string,
  fn: (traceContext: TraceContext, input: Input) => any,
  options?: WrapAgentOptions
) {
  const wrappedFunction = async function (
    this: any,
    input: Input,
    runOptions?: WrapRunOptions
  ) {
    const tracer = trace.getTracer("lemma");
    const runId = uuidv4();
    const isExperiment = resolveIsExperiment(
      isExperimentModeEnabled(),
      options,
      runOptions
    );
    const threadId = normalizeThreadId(runOptions?.threadId);
    const attributes: Record<string, string | boolean> = {
      "ai.agent.name": agentName,
      "lemma.run_id": runId,
      "lemma.is_experiment": isExperiment,
    };
    if (threadId) {
      attributes["lemma.thread_id"] = threadId;
    }

    const span = tracer.startSpan(
      "ai.agent.run",
      {
        attributes,
      },
      ROOT_CONTEXT
    );

    span.setAttribute("ai.agent.input", JSON.stringify(input) ?? "null");

    lemmaDebug("trace-wrapper", "span started", { agentName, runId });

    const ctx = trace.setSpan(ROOT_CONTEXT, span);
    let outputSet = false;

    try {
      return await context.with(ctx, async () => {
        const onComplete = (result: unknown): void => {
          if (outputSet) return;
          span.setAttribute("ai.agent.output", JSON.stringify(result) ?? "null");
          outputSet = true;
          span.end();
          lemmaDebug("trace-wrapper", "onComplete called", { runId });
        };

        const recordError = (error: unknown) => {
          span.recordException(error instanceof Error ? error : new Error(String(error)));
          span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
        };

        const result = await fn.call(this, { span, runId, onComplete, recordError }, input);

        return { result, runId, span };
      });
    } catch (err) {
      span.recordException(err as Error);
      span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
      span.end();
      lemmaDebug("trace-wrapper", "span ended on error", { runId, error: String(err) });
      throw err;
    }
  };

  return wrappedFunction;
}
