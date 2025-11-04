import type { Tracer } from "./tracer";
import { CandidatePromptManager } from "./candidate-prompt-manager";

export interface TraceData {
  trace_id: string;
  spans: Array<{
    timestamp: string;
    trace_id: string;
    span_id: string;
    parent_span_id: string | null;
    name: string;
    kind: string;
    start_time_ns: bigint;
    end_time_ns: bigint | null;
    duration_ms: number | null;
    attributes: Record<string, unknown>;
    status: {
      status_code: string;
      description?: string;
    } | null;
    events: Array<{
      name: string;
      timestamp_ns: bigint;
      attributes: Record<string, unknown>;
    }>;
    resource: Record<string, unknown>;
  }>;
}

/**
 * Wrapper around Tracer that manages candidate prompts and tracks trace_id.
 *
 * Usage:
 *   const traceRunner = new TraceRunner(tracer, { "prompt1": "..." });
 *
 *   await traceRunner.run(async () => {
 *     // ... tracing code ...
 *   });
 *
 *   const traceData = traceRunner.record();
 *   const traceId = traceData.trace_id;
 *   const spans = traceData.spans;
 */
export class TraceRunner {
  private readonly _tracer: Tracer;
  private readonly _cpm: CandidatePromptManager;
  private readonly _candidatePrompts: Record<string, string> | null;
  private _traceId: string | undefined;
  private _contextEntered = false;
  private _alreadyRecorded = false;

  constructor(
    tracer: Tracer,
    candidatePrompts?: Record<string, string> | null
  ) {
    this._tracer = tracer;
    // Use the tracer's CandidatePromptManager to ensure shared context
    this._cpm = tracer.getCandidatePromptManager();
    this._candidatePrompts = candidatePrompts ?? null;
    this._traceId = undefined;
    this._contextEntered = false;
    this._alreadyRecorded = false;
  }

  /**
   * Run a callback with candidate prompts set in the async context.
   *
   * All spans created within this context will be part of the same trace.
   * The trace_id is captured from spans created within the context and can be retrieved via record().
   *
   * @param callback - Function to run within the tracing context
   * @returns Result of the callback
   */
  async run<T>(callback: () => Promise<T> | T): Promise<T> {
    if (this._alreadyRecorded) {
      throw new Error("Cannot enter context after record() has been called");
    }

    // Set up candidate prompts context
    return this._cpm.run(this._candidatePrompts, async () => {
      this._contextEntered = true;

      try {
        const result = await callback();
        // Capture trace_id from tracer after execution completes
        this._traceId = this._tracer.getTraceId();
        return result;
      } finally {
        // Reset state when context exits
        this._contextEntered = false;
      }
    });
  }

  /**
   * Export all spans and return the full trace with all child spans.
   *
   * @returns Dictionary with trace_id and spans
   * @throws Error if called before context is entered or after already recorded
   */
  async record(): Promise<TraceData> {
    if (this._alreadyRecorded) {
      throw new Error(
        "record() can only be called once per TraceRunner instance"
      );
    }

    // Capture trace_id from tracer if we haven't captured it yet
    if (this._traceId === undefined) {
      this._traceId = this._tracer.getTraceId();
    }

    if (this._traceId === undefined) {
      throw new Error(
        "trace_id could not be captured. Ensure spans are created within the context."
      );
    }

    // Force flush all pending spans
    await this._tracer.forceFlush();

    // Get all spans for this trace
    const allSpans = this._tracer.getSpansAsDicts();
    // Filter spans to only include those matching the trace_id
    const traceSpans = allSpans.filter(
      (span) => span.trace_id === this._traceId
    );

    this._alreadyRecorded = true;

    return {
      trace_id: this._traceId,
      spans: traceSpans,
    };
  }
}
