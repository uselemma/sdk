import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LemmaExperimentRunner } from "./runner";

const mockForceFlush = vi.fn();
const mockRegisterOTel = vi.fn();
const mockEnableExperimentMode = vi.fn();
const mockGetTestCases = vi.fn();
const mockRecordResults = vi.fn();

vi.mock("@uselemma/tracing", () => ({
  registerOTel: (...args: unknown[]) => mockRegisterOTel(...args),
  enableExperimentMode: () => mockEnableExperimentMode(),
}));

vi.mock("./client", () => ({
  LemmaExperimentsClient: vi.fn().mockImplementation(() => ({
    getTestCases: mockGetTestCases,
    recordResults: mockRecordResults,
  })),
}));

describe("LemmaExperimentRunner", () => {
  beforeEach(() => {
    vi.stubEnv("LEMMA_API_KEY", "test-key");
    vi.stubEnv("LEMMA_PROJECT_ID", "test-project");
    mockRegisterOTel.mockReturnValue({ forceFlush: mockForceFlush });
    mockForceFlush.mockResolvedValue(undefined);
    mockRecordResults.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it("constructor calls registerOTel and enableExperimentMode", () => {
    new LemmaExperimentRunner();
    expect(mockRegisterOTel).toHaveBeenCalled();
    expect(mockEnableExperimentMode).toHaveBeenCalled();
  });

  it("calls agent with inputData, not full TestCase", async () => {
    const testCases = [
      { id: "tc-1", inputData: { query: "hello" } },
      { id: "tc-2", inputData: { query: "world" } },
    ];
    mockGetTestCases.mockResolvedValue(testCases);

    const agent = vi.fn().mockImplementation(async (input: { query: string }) => {
      return { runId: `run-${input.query}` };
    });

    const runner = new LemmaExperimentRunner();
    await runner.runExperiment({
      experimentId: "exp-1",
      strategyName: "baseline",
      agent,
      progress: false,
    });

    expect(agent).toHaveBeenCalledWith({ query: "hello" });
    expect(agent).toHaveBeenCalledWith({ query: "world" });
    expect(agent).not.toHaveBeenCalledWith(
      expect.objectContaining({ id: expect.any(String) })
    );
  });

  it("excludes failed agents from results", async () => {
    mockGetTestCases.mockResolvedValue([
      { id: "tc-1", inputData: { q: 1 } },
      { id: "tc-2", inputData: { q: 2 } },
      { id: "tc-3", inputData: { q: 3 } },
    ]);

    const agent = vi.fn().mockImplementation(async (input: { q: number }) => {
      if (input.q === 2) throw new Error("fail");
      return { runId: `run-${input.q}` };
    });

    const runner = new LemmaExperimentRunner();
    const summary = await runner.runExperiment({
      experimentId: "exp-1",
      strategyName: "baseline",
      agent,
      progress: false,
    });

    expect(summary).toEqual({ successful: 2, total: 3 });
    expect(mockRecordResults).toHaveBeenCalledWith(
      "exp-1",
      "baseline",
      expect.arrayContaining([
        { runId: "run-1", testCaseId: "tc-1" },
        { runId: "run-3", testCaseId: "tc-3" },
      ])
    );
    expect(mockRecordResults.mock.calls[0][2]).toHaveLength(2);
  });

  it("calls forceFlush before recordResults", async () => {
    mockGetTestCases.mockResolvedValue([{ id: "tc-1", inputData: {} }]);
    const agent = vi.fn().mockResolvedValue({ runId: "run-1" });

    const callOrder: string[] = [];
    mockForceFlush.mockImplementationOnce(async () => {
      callOrder.push("flush");
    });
    mockRecordResults.mockImplementationOnce(async () => {
      callOrder.push("record");
    });

    const runner = new LemmaExperimentRunner();
    await runner.runExperiment({
      experimentId: "exp-1",
      strategyName: "baseline",
      agent,
      progress: false,
    });

    expect(callOrder).toEqual(["flush", "record"]);
  });

  it("recordResults receives correct args", async () => {
    mockGetTestCases.mockResolvedValue([
      { id: "tc-a", inputData: { x: 1 } },
    ]);
    const agent = vi.fn().mockResolvedValue({ runId: "run-xyz" });

    const runner = new LemmaExperimentRunner();
    await runner.runExperiment({
      experimentId: "exp-99",
      strategyName: "my-strategy",
      agent,
      progress: false,
    });

    expect(mockRecordResults).toHaveBeenCalledWith(
      "exp-99",
      "my-strategy",
      [{ runId: "run-xyz", testCaseId: "tc-a" }]
    );
  });

  it("returns correct ExperimentSummary", async () => {
    mockGetTestCases.mockResolvedValue([
      { id: "tc-1", inputData: {} },
      { id: "tc-2", inputData: {} },
    ]);
    const agent = vi.fn().mockResolvedValue({ runId: "run-1" });

    const runner = new LemmaExperimentRunner();
    const summary = await runner.runExperiment({
      experimentId: "exp-1",
      strategyName: "baseline",
      agent,
      progress: false,
    });

    expect(summary).toEqual({ successful: 2, total: 2 });
  });

  it("progress: false skips progress bar", async () => {
    mockGetTestCases.mockResolvedValue([{ id: "tc-1", inputData: {} }]);
    const agent = vi.fn().mockResolvedValue({ runId: "run-1" });

    const runner = new LemmaExperimentRunner();
    const summary = await runner.runExperiment({
      experimentId: "exp-1",
      strategyName: "baseline",
      agent,
      progress: false,
    });

    expect(summary.successful).toBe(1);
    expect(summary.total).toBe(1);
  });

  it("concurrency limits parallel execution", async () => {
    const testCases = [
      { id: "tc-1", inputData: {} },
      { id: "tc-2", inputData: {} },
      { id: "tc-3", inputData: {} },
    ];
    mockGetTestCases.mockResolvedValue(testCases);

    let concurrent = 0;
    let maxConcurrent = 0;
    const agent = vi.fn().mockImplementation(async () => {
      concurrent++;
      maxConcurrent = Math.max(maxConcurrent, concurrent);
      await new Promise((r) => setTimeout(r, 10));
      concurrent--;
      return { runId: "run-1" };
    });

    const runner = new LemmaExperimentRunner();
    await runner.runExperiment({
      experimentId: "exp-1",
      strategyName: "baseline",
      agent,
      concurrency: 2,
      progress: false,
    });

    expect(maxConcurrent).toBeLessThanOrEqual(2);
    expect(agent).toHaveBeenCalledTimes(3);
  });
});
