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
  private topLevelSpanIdByRunId = new Map<RunId, SpanId>();
  private directChildCountByRunId = new Map<RunId, number>();
  private directChildSpanIdToRunId = new Map<SpanId, RunId>();
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
      span.setAttribute("lemma.run_id", runId);
      this.spanIdToRunId.set(spanId, runId);
      this.topLevelSpanIdByRunId.set(runId, spanId);
      this.directChildCountByRunId.set(runId, 0);
      return;
    }

    const parentSpanId = span.parentSpanContext?.spanId;
    if (!parentSpanId) return;

    const runId = this.spanIdToRunId.get(parentSpanId);
    if (!runId) return;

    if (this.topLevelSpanIdByRunId.get(runId) === parentSpanId) {
      this.directChildSpanIdToRunId.set(spanId, runId);
      this.directChildCountByRunId.set(runId, (this.directChildCountByRunId.get(runId) ?? 0) + 1);
    }

    this.spanIdToRunId.set(spanId, runId);
    span.setAttribute("lemma.run_id", runId);
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
    const shouldSkipExport = this.shouldSkipExport(span);
    const directChildRunId = this.directChildSpanIdToRunId.get(spanId);
    if (directChildRunId) {
      this.directChildSpanIdToRunId.delete(spanId);
      const currentCount = this.directChildCountByRunId.get(directChildRunId) ?? 0;
      this.directChildCountByRunId.set(directChildRunId, Math.max(0, currentCount - 1));
    }

    if (!shouldSkipExport) {
      const batch = this.batches.get(runId);
      if (batch) batch.push(span);
      else this.batches.set(runId, [span]);
    }

    if (isTopLevelRun) {
      this.endedRuns.add(runId);
    }

    void this.exportRunBatch(runId, false);
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
    const runId = attributes?.["lemma.run_id"];
    return typeof runId === "string" && runId.length > 0 ? runId : undefined;
  }

  private getInstrumentationScopeName(span: Span | ReadableSpan): string | undefined {
    return (
      span as unknown as {
        instrumentationScope?: { name?: string };
      }
    ).instrumentationScope?.name;
  }

  private shouldSkipExport(span: Span | ReadableSpan): boolean {
    return this.getInstrumentationScopeName(span) === "next.js";
  }

  private async exportRunBatch(runId: RunId, force: boolean): Promise<void> {
    if (!force && (!this.endedRuns.has(runId) || !this.hasNoOpenDirectChildren(runId))) {
      return;
    }

    const batch = this.batches.get(runId);

    this.batches.delete(runId);
    this.endedRuns.delete(runId);
    this.clearRunMapping(runId);

    if (!batch || batch.length === 0) return;

    await new Promise<void>((resolve) => {
      this.exporter.export(batch, () => resolve());
    });
  }

  private hasNoOpenDirectChildren(runId: RunId): boolean {
    return (this.directChildCountByRunId.get(runId) ?? 0) === 0;
  }

  private clearRunMapping(runId: RunId): void {
    for (const [spanId, mappedRunId] of this.spanIdToRunId.entries()) {
      if (mappedRunId === runId) {
        this.spanIdToRunId.delete(spanId);
      }
    }
    for (const [spanId, mappedRunId] of this.directChildSpanIdToRunId.entries()) {
      if (mappedRunId === runId) {
        this.directChildSpanIdToRunId.delete(spanId);
      }
    }
    this.topLevelSpanIdByRunId.delete(runId);
    this.directChildCountByRunId.delete(runId);
  }
}
