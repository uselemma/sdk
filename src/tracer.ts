import { context, type Span, SpanStatusCode, trace } from "@opentelemetry/api";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import { Resource } from "@opentelemetry/resources";
import type { SpanExporter } from "@opentelemetry/sdk-trace-base";
import {
  BasicTracerProvider,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { AsyncLocalStorage } from "node:async_hooks";
import nunjucks from "nunjucks";

import { CandidatePromptManager } from "./candidate-prompt-manager";
import { MemorySpanExporter } from "./exporter";

type AnyFunction<TArgs extends unknown[] = unknown[], TReturn = unknown> = (
  ...args: TArgs
) => TReturn;

/**
 * Span type for tracing different kinds of operations.
 */
export enum SpanType {
  AGENT = "agent",
  NODE = "node",
  TOOL = "tool",
}

/**
 * OpenTelemetry-based tracer that mimics agentbridge API.
 */
export class Tracer {
  private readonly _tracer: ReturnType<typeof trace.getTracer>;
  private readonly _cpm: CandidatePromptManager;
  private readonly _memoryExporter: MemorySpanExporter;
  private readonly _provider: BasicTracerProvider;
  private readonly _currentPromptSpan: AsyncLocalStorage<{ span: Span } | null>;
  private readonly _llmStartTime: AsyncLocalStorage<{ time: number } | null>;

  constructor(
    serviceName: string,
    exporter?: SpanExporter,
    candidatePromptManager?: CandidatePromptManager
  ) {
    const resource = Resource.default().merge(
      new Resource({
        "service.name": serviceName,
      })
    );

    // Always create a memory exporter for TraceRunner to use
    this._memoryExporter = new MemorySpanExporter();

    // Prepare span processors
    const spanProcessors: SimpleSpanProcessor[] = [
      new SimpleSpanProcessor(this._memoryExporter),
    ];
    if (exporter) {
      spanProcessors.push(new SimpleSpanProcessor(exporter));
    }

    // Set up context manager for async context propagation
    const contextManager = new AsyncLocalStorageContextManager();
    contextManager.enable();
    context.setGlobalContextManager(contextManager);

    // Create provider with span processors
    this._provider = new BasicTracerProvider({
      resource,
      spanProcessors,
    });

    // Register provider globally
    this._provider.register();

    this._tracer = trace.getTracer(serviceName);
    this._cpm = candidatePromptManager ?? new CandidatePromptManager();

    // Context-local state for prompt spans and timing
    this._currentPromptSpan = new AsyncLocalStorage<{ span: Span } | null>();
    this._llmStartTime = new AsyncLocalStorage<{ time: number } | null>();
  }

  /**
   * Wraps a function to trace it as a span.
   *
   * @param spanType - Type of span (SpanType.AGENT, SpanType.NODE, or SpanType.TOOL)
   * @param func - Function to wrap
   * @returns Wrapped function
   */
  wrap<TArgs extends unknown[], TReturn>(
    spanType: SpanType,
    func: AnyFunction<TArgs, TReturn>
  ): AnyFunction<TArgs, TReturn> {
    const wrapped = ((...args: TArgs) => {
      // Capture the current context so the span inherits the parent's trace_id
      const currentContext = context.active();
      const span = this._tracer.startSpan(func.name, undefined, currentContext);
      const activeContext = trace.setSpan(currentContext, span);

      span.setAttribute("span.type", spanType);
      span.setAttribute("function.name", func.name);

      // Add input metadata for agent spans
      const inputArgs = args.slice(0);

      try {
        span.setAttribute("function.input", JSON.stringify(inputArgs));
      } catch {
        // Skip if args can't be serialized
      }

      return context.with(activeContext, () => {
        try {
          const result = func(...args);
          if (result instanceof Promise) {
            return result
              .then((res) => {
                try {
                  span.setAttribute("function.result", JSON.stringify(res));
                } catch {
                  // Skip if result can't be serialized
                }
                span.setStatus({ code: SpanStatusCode.OK });
                span.end();
                return res;
              })
              .catch((error: Error) => {
                span.setStatus({
                  code: SpanStatusCode.ERROR,
                  message: error.message,
                });
                span.recordException(error);
                span.end();
                throw error;
              });
          }

          try {
            span.setAttribute("function.result", JSON.stringify(result));
          } catch {
            // Skip if result can't be serialized
          }
          span.setStatus({ code: SpanStatusCode.OK });
          span.end();
          return result;
        } catch (error) {
          const err = error instanceof Error ? error : new Error(String(error));
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: err.message,
          });
          span.recordException(err);
          span.end();
          throw error;
        }
      });
    }) as AnyFunction<TArgs, TReturn>;

    Object.defineProperty(wrapped, "name", { value: func.name });
    return wrapped;
  }

  /**
   * Context manager for tracing prompt rendering and LLM calls.
   *
   * Usage:
   *   const renderedPrompt = await tracer.prompt(
   *     "translation",
   *     promptTemplate,
   *     { premises: [...], conclusion: "..." }
   *   );
   *   const result = await llm.invoke([{ role: "user", content: renderedPrompt }]);
   *   tracer.addLlmOutput(result.content);
   *
   * @param promptName - Name of the prompt
   * @param promptTemplate - Template string (Nunjucks format)
   * @param inputVars - Variables to render into the template
   * @returns Promise that resolves to the rendered prompt
   */
  async prompt(
    promptName: string,
    promptTemplate: string,
    inputVars: Record<string, unknown>
  ): Promise<string> {
    const currentContext = context.active();
    const span = this._tracer.startSpan(promptName, undefined, currentContext);
    const activeContext = trace.setSpan(currentContext, span);

    span.setAttribute("span.type", "prompt");
    span.setAttribute("prompt.name", promptName);
    span.setAttribute("prompt.template", promptTemplate);
    span.setAttribute("prompt.input_vars", JSON.stringify(inputVars));

    // Select effective template (apply candidate override if present) and render
    const [effectiveTemplate, overrideApplied] = this._cpm.getEffectiveTemplate(
      promptName,
      promptTemplate
    );
    span.setAttribute("prompt.override_applied", overrideApplied);

    const renderedPrompt = nunjucks.renderString(effectiveTemplate, inputVars);

    span.setAttribute("prompt.rendered_length", renderedPrompt.length);
    span.addEvent("prompt_rendered");

    const startTime = Date.now();

    // Store span and start time in context for add_llm_output to use
    // Use run() to ensure these are available in the async context
    return this._currentPromptSpan.run({ span }, () => {
      return this._llmStartTime.run({ time: startTime }, () => {
        // Return the rendered prompt with active context
        // The span and time will be available when addLlmOutput is called
        // as long as it's called within this async context
        return context.with(activeContext, async () => {
          return renderedPrompt;
        });
      });
    });
  }

  /**
   * Start a prompt span and return a context manager-like object.
   *
   * Usage:
   *   const promptCtx = tracer.startPrompt("translation", template, vars);
   *   const renderedPrompt = promptCtx.renderedPrompt;
   *   // ... use renderedPrompt ...
   *   tracer.addLlmOutput(result.content);
   *   promptCtx.end();
   *
   * @param promptName - Name of the prompt
   * @param promptTemplate - Template string (Nunjucks format)
   * @param inputVars - Variables to render into the template
   * @returns Object with renderedPrompt and end() method
   */
  startPrompt(
    promptName: string,
    promptTemplate: string,
    inputVars: Record<string, unknown>
  ): {
    renderedPrompt: string;
    span: Span;
    end: () => void;
  } {
    const currentContext = context.active();
    const span = this._tracer.startSpan(promptName, undefined, currentContext);
    const activeContext = trace.setSpan(currentContext, span);

    span.setAttribute("span.type", "prompt");
    span.setAttribute("prompt.name", promptName);
    span.setAttribute("prompt.template", promptTemplate);
    span.setAttribute("prompt.input_vars", JSON.stringify(inputVars));

    // Select effective template (apply candidate override if present) and render
    const [effectiveTemplate, overrideApplied] = this._cpm.getEffectiveTemplate(
      promptName,
      promptTemplate
    );
    span.setAttribute("prompt.override_applied", overrideApplied);

    const renderedPrompt = nunjucks.renderString(effectiveTemplate, inputVars);

    span.setAttribute("prompt.rendered_length", renderedPrompt.length);
    span.addEvent("prompt_rendered");

    const startTime = Date.now();

    // Store span and start time in context for add_llm_output to use
    // Note: These will only be available if addLlmOutput is called
    // within the same async context chain
    this._currentPromptSpan.enterWith({ span });
    this._llmStartTime.enterWith({ time: startTime });

    return {
      renderedPrompt,
      span,
      end: () => {
        span.end();
      },
    };
  }

  /**
   * Add LLM output metadata to the current prompt span.
   *
   * Usage:
   *   tracer.addLLMOutput(result.content);
   *   // or with more metadata:
   *   tracer.addLlmOutput(
   *     result.content,
   *     "gpt-4",
   *     { prompt_tokens: 100, completion_tokens: 50 }
   *   );
   *
   * @param output - LLM output text
   * @param model - Optional model name
   * @param usage - Optional token usage information
   */
  addLLMOutput(
    output: string,
    model?: string,
    usage?: {
      prompt_tokens?: number;
      completion_tokens?: number;
      total_tokens?: number;
    }
  ): void {
    const store = this._currentPromptSpan.getStore();
    const timeStore = this._llmStartTime.getStore();
    const span = store?.span ?? null;
    const startTime = timeStore?.time ?? null;

    if (!span || startTime === null) {
      return;
    }

    const durationMs = Date.now() - startTime;

    span.setAttribute("gen_ai.response", output.slice(0, 1000)); // Truncate
    span.setAttribute("gen_ai.response.length", output.length);
    span.setAttribute("llm.duration_ms", durationMs);

    if (model) {
      span.setAttribute("gen_ai.request.model", model);
    }

    if (usage) {
      span.setAttribute("gen_ai.usage.prompt_tokens", usage.prompt_tokens ?? 0);
      span.setAttribute(
        "gen_ai.usage.completion_tokens",
        usage.completion_tokens ?? 0
      );
      span.setAttribute("gen_ai.usage.total_tokens", usage.total_tokens ?? 0);
    }

    span.addEvent("llm_call_completed", {
      duration_ms: durationMs,
      response_length: output.length,
    });

    span.end();
  }

  /**
   * Get the current active span.
   *
   * @returns Current span or undefined
   */
  getCurrentSpan(): Span | undefined {
    const span = trace.getActiveSpan();
    return span as Span | undefined;
  }

  /**
   * Add metadata to the current span.
   *
   * Usage:
   *   tracer.addMetadata("decision", "True");
   *
   * @param key - Attribute key
   * @param value - Attribute value
   */
  addMetadata(key: string, value: unknown): void {
    const span = this.getCurrentSpan();
    if (span) {
      if (
        typeof value === "string" ||
        typeof value === "number" ||
        typeof value === "boolean"
      ) {
        span.setAttribute(key, value);
      } else if (Array.isArray(value) || typeof value === "object") {
        const serialized = JSON.stringify(value);
        span.setAttribute(key, serialized.slice(0, 1000));
      } else {
        span.setAttribute(key, String(value).slice(0, 1000));
      }
    }
  }

  /**
   * Add an event to the current span.
   *
   * Usage:
   *   tracer.addEvent("processing_started", { item_count: 10 });
   *
   * @param eventName - Name of the event
   * @param attributes - Optional event attributes
   */
  addEvent(
    eventName: string,
    attributes?: Record<string, string | number | boolean>
  ): void {
    const span = this.getCurrentSpan();
    if (span) {
      span.addEvent(eventName, attributes);
    }
  }

  /**
   * Get the trace_id from the current active span.
   *
   * @returns trace_id as a 32-character hexadecimal string, or undefined if not available
   */
  getTraceId(): string | undefined {
    const span = this.getCurrentSpan();
    if (span) {
      return this._formatTraceId(span.spanContext().traceId);
    }
    return undefined;
  }

  /**
   * Helper to format trace ID as 32-character hex string.
   */
  private _formatTraceId(traceId: string): string {
    // Trace ID from OpenTelemetry is already a hex string, but ensure it's 32 chars
    return traceId.padStart(32, "0").slice(0, 32);
  }

  /**
   * Force flush all pending spans.
   */
  async forceFlush(): Promise<void> {
    await this._provider.forceFlush();
  }

  /**
   * Get the candidate prompt manager instance.
   *
   * @returns The CandidatePromptManager instance used by this tracer
   */
  getCandidatePromptManager(): CandidatePromptManager {
    return this._cpm;
  }

  /**
   * Get the memory exporter instance.
   * This is used internally by TraceRunner to access collected spans.
   *
   * @returns The MemorySpanExporter instance
   */
  getMemoryExporter(): MemorySpanExporter {
    return this._memoryExporter;
  }

  /**
   * Clear all spans from memory exporter.
   * Useful for cleaning up between test runs.
   */
  clearSpans(): void {
    this._memoryExporter.clear();
  }
}
