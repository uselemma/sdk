import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { enableExperimentMode, disableExperimentMode } from "./experiment-mode";
import { wrapAgent } from "./trace-wrapper";

const mockStartSpan = vi.fn();
const mockEnd = vi.fn();
const mockRecordException = vi.fn();
const mockSetStatus = vi.fn();
const mockSetAttribute = vi.fn();

vi.mock("@opentelemetry/api", () => ({
  context: {
    with: (_ctx: unknown, fn: () => Promise<unknown>) => fn(),
  },
  trace: {
    getTracer: () => ({
      startSpan: mockStartSpan,
    }),
    setSpan: (_ctx: unknown, span: unknown) => ({}),
  },
  ROOT_CONTEXT: {},
}));

function createMockSpan() {
  const span = {
    end: mockEnd,
    recordException: mockRecordException,
    setStatus: mockSetStatus,
    setAttribute: mockSetAttribute,
  };
  mockStartSpan.mockReturnValue(span);
  return span;
}

describe("wrapAgent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    disableExperimentMode();
    createMockSpan();
  });

  afterEach(() => {
    disableExperimentMode();
  });

  it("creates span with name ai.agent.run", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v);
    await wrapped("hello");

    expect(mockStartSpan).toHaveBeenCalledWith(
      "ai.agent.run",
      expect.any(Object),
      expect.anything()
    );
  });

  it("sets ai.agent.name attribute", async () => {
    const wrapped = wrapAgent("my-agent", async (_ctx, v) => v);
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["ai.agent.name"]).toBe("my-agent");
  });

  it("sets ai.agent.input and ai.agent.output as JSON strings", async () => {
    const wrapped = wrapAgent("my-agent", async (_ctx, v: string) => `out:${v}`);
    await wrapped("hello");

    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.input", '"hello"');
    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.output", '"out:hello"');
  });

  it("lemma.is_experiment is false by default", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v);
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(false);
  });

  it("lemma.is_experiment is true when isExperiment: true", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v, {
      isExperiment: true,
    });
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(true);
  });

  it("lemma.is_experiment is true when enableExperimentMode is active", async () => {
    enableExperimentMode();
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v);
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(true);
  });

  it("invocation options override wrapper isExperiment setting", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v, {
      isExperiment: true,
    });
    await wrapped("x", { isExperiment: false });

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(false);
  });

  it("sets lemma.thread_id when threadId is provided in invocation options", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v);
    await wrapped("x", { threadId: "thread_123" });

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.thread_id"]).toBe("thread_123");
  });

  it("does not set lemma.thread_id for blank threadId values", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v);
    await wrapped("x", { threadId: "   " });

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.thread_id"]).toBeUndefined();
  });

  it("span ends when fn returns", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v);
    await wrapped("hello");

    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  it("ends span when onComplete is called, not when fn returns", async () => {
    let unblock!: () => void;
    const gate = new Promise<void>((resolve) => {
      unblock = resolve;
    });
    const wrapped = wrapAgent("demo-agent", async (ctx) => {
      ctx.onComplete("done");
      await gate;
    });

    const run = wrapped("hello");
    await Promise.resolve();

    expect(mockEnd).toHaveBeenCalledTimes(1);
    unblock();
    await run;
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  it("onComplete sets output; return value ignored for output when onComplete ran", async () => {
    const wrapped = wrapAgent("demo-agent", async (ctx) => {
      ctx.onComplete("done");
      return "ok";
    });

    await wrapped("hello");

    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.output", '"done"');
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  it("returns runId in result", async () => {
    const wrapped = wrapAgent("demo-agent", async (_ctx, v) => v);
    const out = await wrapped("x");

    expect(typeof out.runId).toBe("string");
    expect(out.runId.length).toBeGreaterThan(0);
  });

  it("recordError with Error calls recordException and setStatus", async () => {
    const wrapped = wrapAgent(
      "demo-agent",
      async (ctx) => {
        ctx.recordError(new Error("boom"));
        return "ok";
      }
    );

    await wrapped("x");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockSetStatus).toHaveBeenCalledWith({ code: 2 });
  });

  it("recordError with non-Error wraps in Error", async () => {
    const wrapped = wrapAgent(
      "demo-agent",
      async (ctx) => {
        ctx.recordError("not an error");
        return "ok";
      }
    );

    await wrapped("x");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockRecordException.mock.calls[0][0].message).toBe("not an error");
  });

  it("agent throws - exception recorded, span ended, and error rethrown", async () => {
    const wrapped = wrapAgent("demo-agent", async () => {
      throw new ValueError("sync boom");
    });

    await expect(wrapped("x")).rejects.toThrow("sync boom");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockSetStatus).toHaveBeenCalledWith({ code: 2 });
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });
});

class ValueError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValueError";
  }
}
