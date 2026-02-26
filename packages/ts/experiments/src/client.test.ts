import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LemmaExperimentsClient } from "./client";

describe("LemmaExperimentsClient", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.stubEnv("LEMMA_API_KEY", "test-key");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    globalThis.fetch = originalFetch;
  });

  it("throws when no API key is provided", () => {
    vi.stubEnv("LEMMA_API_KEY", "");
    expect(() => new LemmaExperimentsClient()).toThrow(
      "LemmaExperimentsClient: Missing API key"
    );
  });

  it("getTestCases parses response correctly", async () => {
    const mockCases = [
      { id: "tc-1", inputData: { query: "hello" } },
      { id: "tc-2", inputData: { query: "world" } },
    ];

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCases),
    });

    const client = new LemmaExperimentsClient({ apiKey: "key" });
    const result = await client.getTestCases("exp-123");

    expect(result).toEqual(mockCases);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/experiments/exp-123/test-cases"),
      expect.objectContaining({
        headers: { Authorization: "Bearer key" },
      })
    );
  });

  it("getTestCases throws on non-200", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Not Found",
    });

    const client = new LemmaExperimentsClient({ apiKey: "key" });

    await expect(client.getTestCases("exp-123")).rejects.toThrow(
      "Failed to get test cases: Not Found"
    );
  });

  it("recordResults sends correct method, headers, and body", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true });

    const client = new LemmaExperimentsClient({ apiKey: "key" });
    const results = [
      { runId: "run-1", testCaseId: "tc-1" },
      { runId: "run-2", testCaseId: "tc-2" },
    ];

    await client.recordResults("exp-123", "baseline", results);

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/experiments/exp-123/results"),
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer key",
        },
        body: JSON.stringify({
          strategyName: "baseline",
          results,
        }),
      })
    );
  });

  it("recordResults throws on non-200", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Server Error",
    });

    const client = new LemmaExperimentsClient({ apiKey: "key" });

    await expect(
      client.recordResults("exp-123", "baseline", [
        { runId: "run-1", testCaseId: "tc-1" },
      ])
    ).rejects.toThrow("Failed to record results: Server Error");
  });
});
