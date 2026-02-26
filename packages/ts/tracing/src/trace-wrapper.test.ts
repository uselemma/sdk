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

  it("autoEndRoot: false - onComplete ends span and returns true", async () => {
    let onCompleteReturn: boolean | undefined;
    const wrapped = wrapAgent(
      "demo-agent",
      async (ctx) => {
        onCompleteReturn = ctx.onComplete("done");
        return "ok";
      },
      { autoEndRoot: false }
    );

    const out = await wrapped("hello");

    expect(out.result).toBe("ok");
    expect(out.runId).toBeDefined();
    expect(out.span).toBeDefined();
    expect(onCompleteReturn).toBe(true);
    expect(mockEnd).toHaveBeenCalled();
  });

  it("onComplete called twice - second returns false", async () => {
    const results: boolean[] = [];
    const wrapped = wrapAgent(
      "demo-agent",
      async (ctx) => {
        results.push(ctx.onComplete("a"));
        results.push(ctx.onComplete("b"));
        return "ok";
      },
      { autoEndRoot: false }
    );

    await wrapped("x");

    expect(results[0]).toBe(true);
    expect(results[1]).toBe(false);
    expect(mockEnd).toHaveBeenCalledTimes(1);
  });

  it("autoEndRoot: true - onComplete returns false, span not ended", async () => {
    let onCompleteReturn: boolean | undefined;
    const wrapped = wrapAgent(
      "demo-agent",
      async (ctx) => {
        onCompleteReturn = ctx.onComplete("done");
        return "ok";
      },
      { autoEndRoot: true }
    );

    await wrapped("hello");

    expect(onCompleteReturn).toBe(false);
    expect(mockEnd).not.toHaveBeenCalled();
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

  it("agent throws - exception recorded and rethrown", async () => {
    const wrapped = wrapAgent("demo-agent", async () => {
      throw new ValueError("sync boom");
    });

    await expect(wrapped("x")).rejects.toThrow("sync boom");

    expect(mockRecordException).toHaveBeenCalledWith(expect.any(Error));
    expect(mockSetStatus).toHaveBeenCalledWith({ code: 2 });
  });
});

class ValueError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValueError";
  }
}
