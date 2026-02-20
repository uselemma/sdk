import { randomUUID } from "crypto";
import type { Context } from "@opentelemetry/api";
import {
  type ReadableSpan,
  type Span,
  type SpanExporter,
  type SpanProcessor,
} from "@opentelemetry/sdk-trace-base";

type RunId = string;
type SpanId = string;

export class RunBatchSpanProcessor implements SpanProcessor {
  private isShutdown = false;
  private spanIdToRunId = new Map<SpanId, RunId>();
  private batches = new Map<RunId, ReadableSpan[]>();
  private endedRuns = new Set<RunId>();
  private readonly exporter: SpanExporter;

  constructor(exporter: SpanExporter) {
    this.exporter = exporter;
  }

  onStart(span: Span, _parentContext: Context): void {
    const spanId = span.spanContext().spanId;

    if (this.isTopLevelRun(span)) {
      const runId = this.getRunIdFromSpan(span) ?? randomUUID();
      span.setAttribute("ai.agent.run_id", runId);
      this.spanIdToRunId.set(spanId, runId);
      return;
    }

    const parentSpanId = span.parentSpanContext?.spanId;
    if (!parentSpanId) return;

    const runId = this.spanIdToRunId.get(parentSpanId);
    if (!runId) return;

    this.spanIdToRunId.set(spanId, runId);
    span.setAttribute("ai.agent.run_id", runId);
  }

  onEnd(span: ReadableSpan): void {
    const spanId = span.spanContext().spanId;
    const runId =
      this.spanIdToRunId.get(spanId) ??
      (span.parentSpanContext?.spanId
        ? this.spanIdToRunId.get(span.parentSpanContext.spanId)
        : undefined);

    if (!runId) return;

    const isTopLevelRun = this.isTopLevelRun(span);
    const shouldSkipExport = this.getInstrumentationScopeName(span) === "next.js";

    if (!shouldSkipExport) {
      const batch = this.batches.get(runId);
      if (batch) batch.push(span);
      else this.batches.set(runId, [span]);
    }

    if (isTopLevelRun) {
      this.endedRuns.add(runId);
      void this.exportRunBatch(runId, false);
    }
  }

  async forceFlush(): Promise<void> {
    const runIds = [...this.batches.keys()];
    await Promise.all(runIds.map((runId) => this.exportRunBatch(runId, true)));
    if (this.exporter.forceFlush) {
      await this.exporter.forceFlush();
    }
  }

  async shutdown(): Promise<void> {
    if (this.isShutdown) return;

    this.isShutdown = true;
    await this.forceFlush();
    this.exporter.shutdown();
  }

  private isTopLevelRun(span: Span | ReadableSpan): boolean {
    return span.name === "ai.agent.run" && !span.parentSpanContext;
  }

  private getRunIdFromSpan(span: Span): string | undefined {
    const attributes = (span as unknown as { attributes?: Record<string, unknown> })
      .attributes;
    const runId = attributes?.["ai.agent.run_id"];
    return typeof runId === "string" && runId.length > 0 ? runId : undefined;
  }

  private getInstrumentationScopeName(span: Span | ReadableSpan): string | undefined {
    return (
      span as unknown as {
        instrumentationScope?: { name?: string };
      }
    ).instrumentationScope?.name;
  }

  private async exportRunBatch(runId: RunId, force: boolean): Promise<void> {
    if (!force && !this.endedRuns.has(runId)) return;

    const batch = this.batches.get(runId);

    this.batches.delete(runId);
    this.endedRuns.delete(runId);
    this.clearRunMapping(runId);

    if (!batch || batch.length === 0) return;

    await new Promise<void>((resolve) => {
      this.exporter.export(batch, () => resolve());
    });
  }

  private clearRunMapping(runId: RunId): void {
    for (const [spanId, mappedRunId] of this.spanIdToRunId.entries()) {
      if (mappedRunId === runId) {
        this.spanIdToRunId.delete(spanId);
      }
    }
  }
}
