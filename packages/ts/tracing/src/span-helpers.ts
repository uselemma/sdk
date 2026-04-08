import { trace as otelTrace } from "@opentelemetry/api";
import type { Span } from "@opentelemetry/api";

/**
 * Core helper: wraps `fn` so every call runs inside a child span named
 * `spanName` under the currently active context. Unlike `wrapAgent`, this
 * does NOT create a new trace root — it adds a child span to whatever span
 * is currently active.
 *
 * The span ends when the function returns (or throws). Return values are
 * passed through unchanged. Input and output are automatically recorded as
 * `input.value` and `output.value` span attributes.
 */
function spanHelper<Input = unknown, Output = unknown>(
  spanName: string,
  fn: (input: Input) => Output | Promise<Output>,
  spanType?: string
): (input: Input) => Promise<Output> {
  return async function (input: Input): Promise<Output> {
    const tracer = otelTrace.getTracer("lemma");
    return tracer.startActiveSpan(spanName, async (span: Span) => {
      if (spanType) {
        span.setAttribute("span.type", spanType);
      }
      span.setAttribute("input.value", JSON.stringify(input) ?? "null");
      try {
        const result = await fn(input);
        span.setAttribute("output.value", JSON.stringify(result) ?? "null");
        span.end();
        return result;
      } catch (err) {
        span.recordException(err as Error);
        span.setStatus({ code: 2 }); // SpanStatusCode.ERROR
        span.end();
        throw err;
      }
    });
  };
}

/**
 * Wraps a function with a child span under the current active context.
 *
 * Use this for any internal function you want to appear in the trace — tool
 * implementations, retrieval calls, preprocessing steps, etc.
 *
 * Input and output are automatically captured as span attributes.
 *
 * @param name - Span name shown in the Lemma trace view.
 * @param fn   - Function to wrap. Receives the same input as the returned wrapper.
 *
 * @example
 * const formatOutput = trace("format-output", async (raw: string) => {
 *   return raw.trim().toLowerCase();
 * });
 *
 * // Inside an agent() handler:
 * const formatted = await formatOutput(rawText);
 */
export function trace<Input = unknown, Output = unknown>(
  name: string,
  fn: (input: Input) => Output | Promise<Output>
): (input: Input) => Promise<Output> {
  return spanHelper(name, fn);
}

/**
 * Wraps a tool function with a child span. Sets `span.type = "tool"`.
 * Input and output are automatically captured as `input.value` / `output.value`.
 *
 * @example
 * const lookupOrder = tool("lookup-order", async (orderId: string) => {
 *   return db.orders.findById(orderId);
 * });
 */
export function tool<Input = unknown, Output = unknown>(
  name: string,
  fn: (input: Input) => Output | Promise<Output>
): (input: Input) => Promise<Output> {
  return spanHelper(name, fn, "tool");
}

/**
 * Wraps an LLM call with a child span. Sets `span.type = "generation"`.
 * Input and output are automatically captured as `input.value` / `output.value`.
 *
 * Prefer provider instrumentation (OpenInference) for automatic LLM spans
 * with prompt/completion/token attributes. Use this helper for custom or
 * lightly-instrumented models.
 *
 * @example
 * const generate = llm("gpt-4o", async (prompt: string) => {
 *   return openai.chat.completions.create({ ... });
 * });
 */
export function llm<Input = unknown, Output = unknown>(
  name: string,
  fn: (input: Input) => Output | Promise<Output>
): (input: Input) => Promise<Output> {
  return spanHelper(name, fn, "generation");
}

/**
 * Wraps a retrieval function with a child span. Sets `span.type = "retriever"`.
 * Input and output are automatically captured as `input.value` / `output.value`.
 *
 * @example
 * const search = retrieval("vector-search", async (query: string) => {
 *   return vectorDB.search(query, { topK: 5 });
 * });
 */
export function retrieval<Input = unknown, Output = unknown>(
  name: string,
  fn: (input: Input) => Output | Promise<Output>
): (input: Input) => Promise<Output> {
  return spanHelper(name, fn, "retriever");
}
