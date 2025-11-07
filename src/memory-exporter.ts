import { ExportResultCode } from "@opentelemetry/core";
import type { ReadableSpan, SpanExporter } from "@opentelemetry/sdk-trace-base";

export interface SpanDict {
  timestamp: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: string;
  start_time_ns: string;
  end_time_ns: string | null;
  duration_ms: number | null;
  attributes: Record<string, unknown>;
  status: {
    status_code: string;
    description?: string;
  } | null;
  events: Array<{
    name: string;
    timestamp_ns: string;
    attributes: Record<string, unknown>;
  }>;
  resource: Record<string, unknown>;
}

/**
 * Span exporter that stores spans in memory for retrieval.
 */
export class MemorySpanExporter implements SpanExporter {
  private readonly _spans: ReadableSpan[] = [];

  export(spans: ReadableSpan[]): Promise<{ code: ExportResultCode }> {
    this._spans.push(...spans);
    return Promise.resolve({ code: ExportResultCode.SUCCESS });
  }

  getSpans(): ReadableSpan[] {
    return [...this._spans];
  }

  getSpansAsDicts(): SpanDict[] {
    return this._spans.map((span) => this._spanToDict(span));
  }

  getSpansByTraceId(traceId: string): SpanDict[] {
    const formattedTraceId = this._formatTraceId(traceId);
    return this._spans
      .map((span) => this._spanToDict(span))
      .filter((span) => span.trace_id === formattedTraceId);
  }

  private _formatTraceId(traceId: string): string {
    // Ensure trace ID is 32-character hex string
    return traceId.padStart(32, "0").slice(0, 32);
  }

  private _formatSpanId(spanId: string): string {
    // Ensure span ID is 16-character hex string
    return spanId.padStart(16, "0").slice(0, 16);
  }

  private _spanToDict(span: ReadableSpan): SpanDict {
    const spanCtx = span.spanContext();
    const traceId = this._formatTraceId(spanCtx.traceId);
    const spanId = this._formatSpanId(spanCtx.spanId);
    const parentSpanId = span.parentSpanContext
      ? this._formatSpanId(span.parentSpanContext.spanId)
      : null;

    return {
      timestamp: new Date().toISOString(),
      trace_id: traceId,
      span_id: spanId,
      parent_span_id: parentSpanId,
      name: span.name,
      kind: span.kind.toString(),
      start_time_ns: (
        BigInt(span.startTime[0]) * 1_000_000_000n +
        BigInt(span.startTime[1])
      ).toString(),
      end_time_ns: span.endTime
        ? (
            BigInt(span.endTime[0]) * 1_000_000_000n +
            BigInt(span.endTime[1])
          ).toString()
        : null,
      duration_ms: span.endTime
        ? (span.endTime[0] - span.startTime[0]) * 1000 +
          (span.endTime[1] - span.startTime[1]) / 1_000_000
        : null,
      attributes: span.attributes ? { ...span.attributes } : {},
      status: span.status
        ? {
            status_code: span.status.code.toString(),
            description: span.status.message,
          }
        : null,
      events: (span.events || []).map((event) => ({
        name: event.name,
        timestamp_ns: (
          BigInt(event.time[0]) * 1_000_000_000n +
          BigInt(event.time[1])
        ).toString(),
        attributes: event.attributes ? { ...event.attributes } : {},
      })),
      resource: span.resource?.attributes
        ? { ...span.resource.attributes }
        : {},
    };
  }

  clear(): void {
    this._spans.length = 0;
  }

  shutdown(): Promise<void> {
    return Promise.resolve();
  }

  forceFlush(): Promise<void> {
    return Promise.resolve();
  }
}
