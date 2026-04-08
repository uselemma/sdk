import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { enableExperimentMode, disableExperimentMode } from "./experiment-mode";
import { agent, wrapAgent } from "./trace-wrapper";

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

describe("agent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    disableExperimentMode();
    createMockSpan();
  });

  afterEach(() => {
    disableExperimentMode();
  });

  it("creates span with name ai.agent.run", async () => {
    const wrapped = agent("demo-agent", async (v) => v);
    await wrapped("hello");

    expect(mockStartSpan).toHaveBeenCalledWith(
      "ai.agent.run",
      expect.any(Object),
      expect.anything()
    );
  });

  it("sets ai.agent.name attribute", async () => {
    const wrapped = agent("my-agent", async (v) => v);
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["ai.agent.name"]).toBe("my-agent");
  });

  it("auto-closes and captures return value when complete() is not called", async () => {
    const wrapped = agent("demo-agent", async (v: string) => `out:${v}`);
    await wrapped("hello");

    expect(mockEnd).toHaveBeenCalledTimes(1);
    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.output", '"out:hello"');
  });

  it("sets ai.agent.input and ai.agent.output as JSON strings", async () => {
    const wrapped = agent("my-agent", async (v: string) => `out:${v}`);
    await wrapped("hello");

    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.input", '"hello"');
    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.output", '"out:hello"');
  });

  it("lemma.is_experiment is false by default", async () => {
    const wrapped = agent("demo-agent", async (v) => v);
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(false);
  });

  it("lemma.is_experiment is true when isExperiment: true", async () => {
    const wrapped = agent("demo-agent", async (v) => v, {
      isExperiment: true,
    });
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(true);
  });

  it("lemma.is_experiment is true when enableExperimentMode is active", async () => {
    enableExperimentMode();
    const wrapped = agent("demo-agent", async (v) => v);
    await wrapped("x");

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(true);
  });

  it("invocation options override wrapper isExperiment setting", async () => {
    const wrapped = agent("demo-agent", async (v) => v, {
      isExperiment: true,
    });
    await wrapped("x", { isExperiment: false });

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.is_experiment"]).toBe(false);
  });

  it("sets lemma.thread_id when threadId is provided in invocation options", async () => {
    const wrapped = agent("demo-agent", async (v) => v);
    await wrapped("x", { threadId: "thread_123" });

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.thread_id"]).toBe("thread_123");
  });

  it("does not set lemma.thread_id for blank threadId values", async () => {
    const wrapped = agent("demo-agent", async (v) => v);
    await wrapped("x", { threadId: "   " });

    const call = mockStartSpan.mock.calls[0];
    expect(call[1].attributes["lemma.thread_id"]).toBeUndefined();
  });

  it("complete() ends span before fn returns; auto-complete on return is a no-op", async () => {
    let unblock!: () => void;
    const gate = new Promise<void>((resolve) => {
      unblock = resolve;
    });
    const wrapped = agent("demo-agent", async (_input, ctx) => {
      ctx.complete("done");
      await gate;
    });

    const run = wrapped("hello");
    await Promise.resolve();

    expect(mockEnd).toHaveBeenCalledTimes(1);
    unblock();
    await run;
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  it("explicit complete() overrides return value as output", async () => {
    const wrapped = agent("demo-agent", async (_input, ctx) => {
      ctx.complete("explicit-output");
      return "return-value";
    });

    await wrapped("hello");

    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.output", '"explicit-output"');
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  it("returns runId in result", async () => {
    const wrapped = agent("demo-agent", async (v) => v);
    const out = await wrapped("x");

    expect(typeof out.runId).toBe("string");
    expect(out.runId.length).toBeGreaterThan(0);
  });

  it("fail() with Error calls recordException and setStatus", async () => {
    const wrapped = agent(
      "demo-agent",
      async (_input, ctx) => {
        ctx.fail(new Error("boom"));
        return "ok";
      }
    );

    await wrapped("x");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockSetStatus).toHaveBeenCalledWith({ code: 2 });
  });

  it("fail() with non-Error wraps in Error", async () => {
    const wrapped = agent(
      "demo-agent",
      async (_input, ctx) => {
        ctx.fail("not an error");
        return "ok";
      }
    );

    await wrapped("x");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockRecordException.mock.calls[0][0].message).toBe("not an error");
  });

  it("onComplete() and recordError() are deprecated aliases that still work", async () => {
    const wrapped = agent(
      "demo-agent",
      async (_input, ctx) => {
        ctx.recordError(new Error("boom"));
        ctx.onComplete("legacy-output");
        return "return-value";
      }
    );

    await wrapped("x");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.output", '"legacy-output"');
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  it("agent throws — exception recorded, span ended, error rethrown", async () => {
    const wrapped = agent("demo-agent", async () => {
      throw new ValueError("sync boom");
    });

    await expect(wrapped("x")).rejects.toThrow("sync boom");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockSetStatus).toHaveBeenCalledWith({ code: 2 });
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  describe("streaming: true", () => {
    it("span stays open when function returns without calling complete()", async () => {
      const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const wrapped = agent("demo-agent", async (v) => v, { streaming: true });
      const { span } = await wrapped("hello");

      expect(mockEnd).not.toHaveBeenCalled();
      expect((span as any).ended).toBeFalsy();
      spy.mockRestore();
    });

    it("emits a console warning when streaming agent returns without complete()", async () => {
      const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const wrapped = agent("streaming-agent", async (v) => v, { streaming: true });
      await wrapped("hello");

      expect(spy).toHaveBeenCalledWith(expect.stringContaining("streaming-agent"));
      spy.mockRestore();
    });

    it("complete() closes the span and captures output in streaming mode", async () => {
      const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const wrapped = agent("demo-agent", async (v: string, ctx) => {
        ctx.complete(`out:${v}`);
        return "stream-response";
      }, { streaming: true });

      await wrapped("hello");

      expect(mockSetAttribute).toHaveBeenCalledWith("ai.agent.output", '"out:hello"');
      expect(mockEnd).toHaveBeenCalledTimes(1);
      spy.mockRestore();
    });

    it("no console warning when complete() is called before streaming function returns", async () => {
      const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const wrapped = agent("demo-agent", async (v: string, ctx) => {
        ctx.complete(v);
        return "stream-response";
      }, { streaming: true });

      await wrapped("hello");

      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    });
  });
});

describe("wrapAgent (deprecated alias)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    disableExperimentMode();
    createMockSpan();
  });

  it("wrapAgent is identical to agent", () => {
    expect(wrapAgent).toBe(agent);
  });

  it("still works as a drop-in replacement", async () => {
    const wrapped = wrapAgent("demo-agent", async (v) => v);
    const { result, runId } = await wrapped("hello");
    expect(result).toBe("hello");
    expect(typeof runId).toBe("string");
  });
});

class ValueError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValueError";
  }
}
