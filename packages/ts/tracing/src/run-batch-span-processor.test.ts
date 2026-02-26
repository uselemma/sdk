import { describe, it, expect } from "vitest";
import { RunBatchSpanProcessor } from "./run-batch-span-processor";

type FakeSpan = {
  name: string;
  spanId: string;
  parentSpanId?: string;
  scopeName?: string;
  attributes: Record<string, unknown>;
  ended: boolean;
  spanContext: () => { spanId: string };
  parentSpanContext?: { spanId: string } | null;
  instrumentationScope?: { name?: string };
  setAttribute: (k: string, v: unknown) => void;
  end: () => void;
};

function createFakeSpan(
  name: string,
  spanId: string,
  opts: { parentSpanId?: string; scopeName?: string; attributes?: Record<string, unknown> } = {}
): FakeSpan {
  const attrs = { ...opts.attributes };
  return {
    name,
    spanId,
    parentSpanId: opts.parentSpanId,
    scopeName: opts.scopeName ?? "lemma",
    attributes: attrs,
    ended: false,
    spanContext: () => ({ spanId }),
    parentSpanContext: opts.parentSpanId ? { spanId: opts.parentSpanId } : undefined,
    instrumentationScope: { name: opts.scopeName ?? "lemma" },
    setAttribute(k: string, v: unknown) {
      attrs[k] = v;
    },
    end() {
      this.ended = true;
    },
  };
}

function createExporter() {
  const exports: FakeSpan[][] = [];
  let forceFlushCalls = 0;
  let shutdownCalls = 0;
  return {
    exports,
    forceFlushCalls,
    shutdownCalls,
    export(spans: FakeSpan[], callback: () => void) {
      exports.push([...spans]);
      callback();
    },
    forceFlush: async () => {
      forceFlushCalls++;
    },
    shutdown: () => {
      shutdownCalls++;
    },
    getExportCount: () => exports.length,
    getForceFlushCalls: () => forceFlushCalls,
    getShutdownCalls: () => shutdownCalls,
  };
}

describe("RunBatchSpanProcessor", () => {
  it("batches root span and exports when it ends with no open direct children", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", {
      attributes: { "lemma.run_id": "run-a" },
    });

    processor.onStart(root as any, undefined as any);
    processor.onEnd(root as any);

    await new Promise((r) => setTimeout(r, 0));

    expect(exporter.exports.length).toBe(1);
    expect(exporter.exports[0].map((s) => s.spanId)).toContain("1");
  });

  it("auto-ends root when last direct child ends", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", {
      attributes: { "lemma.run_id": "run-a", "lemma.auto_end_root": true },
    });
    const child = createFakeSpan("ai.step", "2", { parentSpanId: "1" });

    processor.onStart(root as any, undefined as any);
    processor.onStart(child as any, undefined as any);
    processor.onEnd(child as any);
    processor.onEnd(root as any);

    await new Promise((r) => setTimeout(r, 0));

    expect(exporter.exports.length).toBe(1);
    expect(root.ended).toBe(true);
  });

  it("skips next.js scoped spans from export", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "10", {
      attributes: { "lemma.run_id": "run-next" },
    });
    const nextjs = createFakeSpan("middleware", "11", {
      parentSpanId: "10",
      scopeName: "next.js",
    });

    processor.onStart(root as any, undefined as any);
    processor.onStart(nextjs as any, undefined as any);
    processor.onEnd(nextjs as any);
    processor.onEnd(root as any);

    await new Promise((r) => setTimeout(r, 0));

    expect(exporter.exports.length).toBe(1);
    expect(exporter.exports[0].map((s) => s.spanId)).toEqual(["10"]);
  });

  it("waits for direct child that ends after root", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "100", {
      attributes: { "lemma.run_id": "run-late" },
    });
    const child = createFakeSpan("ai.step", "101", { parentSpanId: "100" });

    processor.onStart(root as any, undefined as any);
    processor.onStart(child as any, undefined as any);
    processor.onEnd(root as any);

    expect(exporter.exports.length).toBe(0);

    processor.onEnd(child as any);

    await new Promise((r) => setTimeout(r, 0));

    expect(exporter.exports.length).toBe(1);
    expect(exporter.exports[0].map((s) => s.spanId)).toContain("100");
    expect(exporter.exports[0].map((s) => s.spanId)).toContain("101");
  });

  it("forceFlush exports each run in separate batch", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const run1 = createFakeSpan("ai.agent.run", "20", {
      attributes: { "lemma.run_id": "run-1" },
    });
    const run2 = createFakeSpan("ai.agent.run", "30", {
      attributes: { "lemma.run_id": "run-2" },
    });
    const child1 = createFakeSpan("child", "21", { parentSpanId: "20" });
    const child2 = createFakeSpan("child", "31", { parentSpanId: "30" });

    processor.onStart(run1 as any, undefined as any);
    processor.onStart(run2 as any, undefined as any);
    processor.onStart(child1 as any, undefined as any);
    processor.onStart(child2 as any, undefined as any);
    processor.onEnd(child1 as any);
    processor.onEnd(child2 as any);

    await processor.forceFlush();

    expect(exporter.exports.length).toBe(2);
  });

  it("shutdown calls forceFlush and exporter.shutdown", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    await processor.shutdown();

    expect(exporter.getForceFlushCalls()).toBe(1);
    expect(exporter.getShutdownCalls()).toBe(1);
  });

  it("shutdown is idempotent", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    await processor.shutdown();
    await processor.shutdown();

    expect(exporter.getShutdownCalls()).toBe(1);
  });

  it("grandchild span is attributed to run", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", {
      attributes: { "lemma.run_id": "run-a" },
    });
    const child = createFakeSpan("ai.step", "2", { parentSpanId: "1" });
    const grandchild = createFakeSpan("ai.substep", "3", { parentSpanId: "2" });

    processor.onStart(root as any, undefined as any);
    processor.onStart(child as any, undefined as any);
    processor.onStart(grandchild as any, undefined as any);
    processor.onEnd(grandchild as any);
    processor.onEnd(child as any);
    processor.onEnd(root as any);

    await new Promise((r) => setTimeout(r, 0));

    expect(exporter.exports.length).toBe(1);
    const ids = exporter.exports[0].map((s) => s.spanId);
    expect(ids).toContain("1");
    expect(ids).toContain("2");
    expect(ids).toContain("3");
  });

  it("root without lemma.run_id gets auto-generated UUID", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", { attributes: {} });

    processor.onStart(root as any, undefined as any);

    expect(root.attributes["lemma.run_id"]).toBeDefined();
    expect(typeof root.attributes["lemma.run_id"]).toBe("string");
    expect((root.attributes["lemma.run_id"] as string).length).toBeGreaterThan(0);

    processor.onEnd(root as any);

    await new Promise((r) => setTimeout(r, 0));

    expect(exporter.exports.length).toBe(1);
  });

  it("forceFlush with no pending batches is a no-op", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    await processor.forceFlush();

    expect(exporter.exports.length).toBe(0);
  });

  it("onStart with no parent returns early", () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const span = createFakeSpan("other.span", "1", {});
    span.parentSpanContext = null;

    processor.onStart(span as any, undefined as any);

    expect(exporter.exports.length).toBe(0);
  });

  it("onStart with parent not in map returns early", () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const span = createFakeSpan("child", "2", { parentSpanId: "999" });

    processor.onStart(span as any, undefined as any);

    expect(exporter.exports.length).toBe(0);
  });

  it("root with lemma.run_id as non-string gets auto-generated UUID", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", {
      attributes: { "lemma.run_id": 123 as any },
    });

    processor.onStart(root as any, undefined as any);

    expect(typeof root.attributes["lemma.run_id"]).toBe("string");
    processor.onEnd(root as any);
    await new Promise((r) => setTimeout(r, 0));
  });

  it("root with attributes undefined gets auto-generated UUID", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", { attributes: {} });
    const stored: Record<string, unknown> = {};
    (root as any).attributes = undefined;
    (root as any).setAttribute = (k: string, v: unknown) => {
      stored[k] = v;
    };

    processor.onStart(root as any, undefined as any);

    expect(stored["lemma.run_id"]).toBeDefined();
    processor.onEnd(root as any);
    await new Promise((r) => setTimeout(r, 0));
  });

  it("span with instrumentationScope undefined is not skipped", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", {
      attributes: { "lemma.run_id": "run-s" },
    });
    const child = createFakeSpan("child", "2", { parentSpanId: "1" });
    (child as any).instrumentationScope = undefined;

    processor.onStart(root as any, undefined as any);
    processor.onStart(child as any, undefined as any);
    processor.onEnd(child as any);
    processor.onEnd(root as any);

    await new Promise((r) => setTimeout(r, 0));
    expect(exporter.exports.length).toBe(1);
  });

  it("onEnd with no runId returns early", () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const span = createFakeSpan("orphan", "1", {});
    span.parentSpanContext = null;

    processor.onEnd(span as any);

    expect(exporter.exports.length).toBe(0);
  });

  it("onEnd gets runId from parent when span not in map", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", {
      attributes: { "lemma.run_id": "run-x" },
    });
    const child = createFakeSpan("child", "2", { parentSpanId: "1" });

    processor.onStart(root as any, undefined as any);
    processor.onEnd(child as any);
    processor.onEnd(root as any);

    await new Promise((r) => setTimeout(r, 0));

    expect(exporter.exports.length).toBe(1);
  });

  it("exportRunBatch with empty batch skips export", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    (processor as any).batches.set("empty-run", []);
    await (processor as any).exportRunBatch("empty-run", true);

    expect(exporter.exports.length).toBe(0);
  });

  it("forceFlush clears direct child mapping", async () => {
    const exporter = createExporter();
    const processor = new RunBatchSpanProcessor(exporter as any);

    const root = createFakeSpan("ai.agent.run", "1", {
      attributes: { "lemma.run_id": "run-flush" },
    });
    const child = createFakeSpan("child", "2", { parentSpanId: "1" });

    processor.onStart(root as any, undefined as any);
    processor.onStart(child as any, undefined as any);
    processor.onEnd(root as any);
    await processor.forceFlush();

    expect(exporter.exports.length).toBe(1);
    expect((processor as any).directChildSpanIdToRunId.size).toBe(0);
  });
});
