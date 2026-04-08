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
   * Override the run output and close the span immediately.
   *
   * In non-streaming agents, `complete()` is **optional** — the wrapper
   * automatically captures the return value as `ai.agent.output` and closes
   * the span when the function returns. Call it explicitly only when you need
   * to record a different output than the return value, or close the span
   * before the function exits.
   *
   * In streaming agents (`{ streaming: true }`), `complete()` is **required**
   * — call it inside the stream's `onFinish` callback once the full output is
   * assembled.
   *
   * Idempotent: the first call wins, subsequent calls are no-ops.
   */
  complete: (result?: unknown) => void;
  /**
   * @deprecated Use {@link complete} instead.
   */
  onComplete: (result: unknown) => void;
  /**
   * Record an error on the span and mark the run as failed.
   * Does not close the span — the wrapper handles closing on return or error.
   */
  fail: (error: unknown) => void;
  /**
   * @deprecated Use {@link fail} instead.
   */
  recordError: (error: unknown) => void;
};

export type WrapAgentOptions = {
  /** Mark this run as an experiment in Lemma. */
  isExperiment?: boolean;
  /**
   * Set to `true` for agents that return a streaming response before the
   * full output is known.
   *
   * When `true`, the wrapper does **not** auto-close the span on function
   * return. You must call `ctx.complete(output)` inside the stream's
   * `onFinish` callback once the full output is assembled.
   *
   * @default false
   */
  streaming?: boolean;
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
 * **Non-streaming (default):** simply return a value from the wrapped function.
 * The wrapper captures it as `ai.agent.output` and closes the span automatically.
 * No call to `ctx.complete()` is needed.
 *
 * **Streaming:** pass `{ streaming: true }` as the third argument. The wrapper
 * will not auto-close the span on return; call `ctx.complete(output)` inside
 * the stream's `onFinish` callback once the full output is assembled.
 *
 * @example
 * // Non-streaming — just return a value
 * const myAgent = agent('my-agent', async (input: string) => {
 *   const { text } = await generateText({
 *     model: openai('gpt-4o'), prompt: input,
 *     experimental_telemetry: { isEnabled: true },
 *   });
 *   return text; // wrapper auto-captures and closes the span
 * });
 *
 * @example
 * // Streaming — opt into manual lifecycle
 * const streamingAgent = agent('streaming-agent', async (input: string, ctx) => {
 *   const result = await streamText({
 *     model: openai('gpt-4o'), prompt: input,
 *     experimental_telemetry: { isEnabled: true },
 *     onFinish({ text }) { ctx.complete(text); },
 *   });
 *   return result.toDataStreamResponse();
 * }, { streaming: true });
 *
 * @param agentName - Human-readable agent name recorded as `ai.agent.name`.
 * @param fn - The agent function to wrap. Receives the call-time input as its
 *   first argument and an optional {@link TraceContext} as its second.
 * @param options - Configuration for the agent trace.
 * @returns An async function that accepts an `input`, executes `fn` inside a
 *   traced context, and returns `{ result, runId, span }`.
 */
export function agent<Input = unknown>(
  agentName: string,
  fn: (input: Input, traceContext: TraceContext) => any,
  options?: WrapAgentOptions
) {
  const streaming = options?.streaming ?? false;

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
      { attributes },
      ROOT_CONTEXT
    );

    span.setAttribute("ai.agent.input", JSON.stringify(input) ?? "null");

    lemmaDebug("trace-wrapper", "span started", { agentName, runId });

    const ctx = trace.setSpan(ROOT_CONTEXT, span);
    let outputSet = false;

    try {
      return await context.with(ctx, async () => {
        const complete = (result?: unknown): void => {
          if (outputSet) return;
          span.setAttribute("ai.agent.output", JSON.stringify(result) ?? "null");
          outputSet = true;
          span.end();
          lemmaDebug("trace-wrapper", "complete called", { runId });
        };

        const fail = (error: unknown): void => {
          span.recordException(error instanceof Error ? error : new Error(String(error)));
          span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
        };

        const traceCtx: TraceContext = {
          span,
          runId,
          complete,
          onComplete: complete,
          fail,
          recordError: fail,
        };

        const result = await fn.call(this, input, traceCtx);

        if (!streaming && !outputSet) {
          complete(result);
        } else if (streaming && !outputSet) {
          lemmaDebug("trace-wrapper", "streaming agent returned without complete()", { agentName, runId });
          console.warn(
            `[lemma] Streaming agent "${agentName}" returned without calling ctx.complete(). ` +
            `Call ctx.complete(output) inside the stream's onFinish callback to close the run span.`
          );
        }

        return { result, runId, span };
      });
    } catch (err) {
      span.recordException(err as Error);
      span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
      if (!outputSet) {
        outputSet = true;
        span.end();
      }
      lemmaDebug("trace-wrapper", "span ended on error", { runId, error: String(err) });
      throw err;
    }
  };

  return wrappedFunction;
}

/**
 * @deprecated Use {@link agent} instead. `wrapAgent` will be removed in a future major version.
 */
export const wrapAgent = agent;
