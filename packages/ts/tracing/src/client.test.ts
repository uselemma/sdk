import { describe, expect, it, vi } from "vitest";
import { Lemma, active } from "./client";

function jsonBody(call: unknown[]) {
  return JSON.parse(String((call[1] as RequestInit).body));
}

describe("Lemma", () => {
  it("posts a completed trace with one-off generation and tool events", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      baseUrl: "https://api.example.test/",
      fetch: fetchMock as typeof fetch,
    });

    const result = await lemma.trace(
      {
        name: "support-agent",
        durationMs: 1234,
        input: "where is my order?",
        threadId: "thread-1",
        userId: "user-1",
      },
      async (trace) => {
        trace.recordTool({
          name: "search_docs",
          input: { query: "order" },
          output: { status: "shipped" },
          durationMs: 25,
          toolParameters: { query: "string" },
        });
        active().recordGeneration({
          name: "draft-reply",
          input: "prompt",
          output: "answer",
          model: "gpt-4o",
          usage: { inputTokens: 12, outputTokens: 8 },
          durationMs: 40,
          llmInvocationParameters: { temperature: 0.2 },
          llmInputMessages: [{ role: "user", content: "where is my order?" }],
        });
        return "it arrives Friday";
      },
    );

    expect(result).toBe("it arrives Friday");
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/traces/ingest",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer key",
          "Content-Type": "application/json",
        }),
      }),
    );

    const body = jsonBody(fetchMock.mock.calls[0]);
    expect(body.project_id).toBe("10000000-0000-0000-0000-000000000001");
    expect(body.trace).toMatchObject({
      name: "support-agent",
      input: "where is my order?",
      output: "it arrives Friday",
      thread_id: "thread-1",
      user_id: "user-1",
      duration_ms: 1234,
    });
    expect(body.trace.spans).toMatchObject([
      {
        name: "search_docs",
        type: "tool",
        input: { query: "order" },
        output: { status: "shipped" },
        duration_ms: 25,
        attributes: {
          "tool.parameters": JSON.stringify({ query: "string" }),
        },
      },
      {
        name: "draft-reply",
        type: "generation",
        model: "gpt-4o",
        usage: { input_tokens: 12, output_tokens: 8 },
        duration_ms: 40,
        attributes: {
          "llm.invocation_parameters": JSON.stringify({ temperature: 0.2 }),
          "llm.input_messages.0.message.role": "user",
          "llm.input_messages.0.message.content": "where is my order?",
          "llm.model_name": "gpt-4o",
          "llm.token_count.prompt": 12,
          "llm.token_count.completion": 8,
        },
      },
    ]);
  });

  it("supports live span handles", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    await lemma.trace("support-agent", async (trace) => {
      const span = trace.startSpan({ name: "retrieve", input: "q" });
      span.end({
        output: ["doc"],
        durationMs: 250,
        retrievalDocuments: [
          { id: "doc-1", content: "shipping policy", score: 0.9 },
        ],
      });
      return "ok";
    });

    const body = jsonBody(fetchMock.mock.calls[0]);
    expect(body.trace.spans[0]).toMatchObject({
      name: "retrieve",
      type: "span",
      input: "q",
      output: ["doc"],
      duration_ms: 250,
      attributes: {
        "retrieval.documents.0.document.id": "doc-1",
        "retrieval.documents.0.document.content": "shipping policy",
        "retrieval.documents.0.document.score": 0.9,
      },
    });
    expect(body.trace.spans[0].id).toEqual(expect.any(String));
  });

  it("supports trace handles with nested span methods", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    const trace = lemma.trace({ name: "support-agent", input: "hi" });
    const span = trace.startSpan("parent span");
    span.recordTool("tool call");
    span.recordGeneration({ name: "answer", model: "gpt-4o", output: "hello" });
    span.end({ output: "done" });
    await trace.end({ output: "hello", durationMs: 321 });

    const body = jsonBody(fetchMock.mock.calls.at(-1)!);
    expect(body.replace).toBe(true);
    expect(body.trace.id).toBe(trace.id);
    expect(body.trace.output).toBe("hello");
    expect(body.trace.duration_ms).toBe(321);
    expect(body.trace.spans).toMatchObject([
      {
        id: span.id,
        name: "parent span",
        type: "span",
        output: "done",
      },
      {
        parent_id: span.id,
        name: "tool call",
        type: "tool",
      },
      {
        parent_id: span.id,
        name: "answer",
        type: "generation",
        model: "gpt-4o",
      },
    ]);
    expect(body.trace.spans[1]).not.toHaveProperty("duration_ms");
    expect(body.trace.spans[2]).not.toHaveProperty("duration_ms");
  });

  it("supports live tool and generation handles", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    await lemma.trace("support-agent", async (trace) => {
      const tool = trace.startTool({
        name: "search_docs",
        input: { query: "order" },
      });
      tool.end({ output: [{ title: "Shipping" }], durationMs: 25 });

      const generation = trace.startGeneration({
        name: "answer",
        model: "gpt-4o",
        input: "prompt",
      });
      generation.end({ output: "It arrives Friday.", durationMs: 40 });

      return "ok";
    });

    const body = jsonBody(fetchMock.mock.calls[0]);
    expect(body.trace.spans).toMatchObject([
      {
        id: expect.any(String),
        name: "search_docs",
        type: "tool",
        input: { query: "order" },
        output: [{ title: "Shipping" }],
        duration_ms: 25,
      },
      {
        id: expect.any(String),
        name: "answer",
        type: "generation",
        model: "gpt-4o",
        input: "prompt",
        output: "It arrives Friday.",
        duration_ms: 40,
      },
    ]);
  });

  it("supports no-argument trace handles with nested shorthand observations", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    const trace = lemma.trace();
    const span = trace.startSpan("parent span");
    span.recordTool("tool call");
    await trace.flush();

    const body = jsonBody(fetchMock.mock.calls.at(-1)!);
    expect(body.trace).toMatchObject({
      id: trace.id,
      name: "trace",
    });
    expect(body.trace.spans).toMatchObject([
      {
        id: span.id,
        name: "parent span",
        type: "span",
      },
      {
        parent_id: span.id,
        name: "tool call",
        type: "tool",
      },
    ]);
    expect(body.trace.spans[0]).not.toHaveProperty("duration_ms");
    expect(body.trace.spans[1]).not.toHaveProperty("duration_ms");
  });

  it("supports client-level detached observations by trace id", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    const trace = lemma.trace();
    const span = lemma.startSpan({ traceId: trace.id });
    lemma.recordTool({
      traceId: trace.id,
      parentSpanId: span.id,
      name: "tool call",
    });
    span.end();
    await trace.flush();

    const body = jsonBody(fetchMock.mock.calls.at(-1)!);
    expect(body.trace.name).toBe("trace");
    expect(body.trace.spans).toMatchObject([
      {
        id: span.id,
        name: "span",
        type: "span",
      },
      {
        parent_id: span.id,
        name: "tool call",
        type: "tool",
      },
    ]);
  });

  it("warns and no-ops detached observations without a trace id", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    const span = lemma.recordSpan({ name: "orphan" });
    lemma.recordTool({ name: "orphan tool" });
    lemma.recordGeneration({ name: "orphan generation" });

    expect(span.id).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalledWith(
      "@uselemma/tracing: span handle requires traceId; skipping span",
    );
    expect(warn).toHaveBeenCalledWith(
      "@uselemma/tracing: tool handle requires traceId; skipping tool",
    );
    expect(warn).toHaveBeenCalledWith(
      "@uselemma/tracing: generation handle requires traceId; skipping generation",
    );

    warn.mockRestore();
  });

  it("warns and no-ops detached observations for unknown trace ids", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    const span = lemma.startSpan({ traceId: "missing-trace", name: "orphan" });

    expect(span.id).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalledWith(
      '@uselemma/tracing: unknown trace id "missing-trace"; skipping span',
    );

    warn.mockRestore();
  });

  it("warns and no-ops detached child observations without parentSpanId", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    const trace = lemma.trace();
    const span = lemma.startSpan({
      traceId: trace.id,
      parentId: "parent-span",
      name: "child span",
    });
    lemma.recordTool({
      traceId: trace.id,
      parentId: "parent-span",
      name: "child tool",
    });
    await trace.flush();

    const body = jsonBody(fetchMock.mock.calls.at(-1)!);
    expect(span.id).toBe("");
    expect(body.trace.spans).toEqual([]);
    expect(warn).toHaveBeenCalledWith(
      "@uselemma/tracing: span has a parent, but parentSpanId was not provided; skipping span",
    );
    expect(warn).toHaveBeenCalledWith(
      "@uselemma/tracing: tool has a parent, but parentSpanId was not provided; skipping tool",
    );

    warn.mockRestore();
  });

  it("flushes failed traces and rethrows the original error", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    await expect(
      lemma.trace("support-agent", async (trace) => {
        trace.recordTool({ name: "lookup", error: new Error("missing") });
        throw new Error("boom");
      }),
    ).rejects.toThrow("boom");

    const body = jsonBody(fetchMock.mock.calls[0]);
    expect(body.trace.status).toBe("ERROR");
    expect(body.trace.error).toBe("boom");
    expect(body.trace.spans[0]).toMatchObject({
      name: "lookup",
      type: "tool",
      status: "ERROR",
      error: "missing",
    });
  });

  it("surfaces ingest failures", async () => {
    const fetchMock = vi.fn(async () => new Response("nope", { status: 503 }));
    const lemma = new Lemma({
      apiKey: "key",
      projectId: "10000000-0000-0000-0000-000000000001",
      fetch: fetchMock as typeof fetch,
    });

    await expect(
      lemma.trace("support-agent", async () => "ok"),
    ).rejects.toThrow("failed to ingest trace (503): nope");
  });
});
