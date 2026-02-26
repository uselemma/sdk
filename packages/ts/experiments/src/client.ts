import type { ExperimentResult, TestCase } from "./types";

export interface LemmaExperimentsClientOptions {
  apiKey?: string;
  baseUrl?: string;
}

const DEFAULT_BASE_URL = "https://api.uselemma.ai";

export class LemmaExperimentsClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;

  constructor(options: LemmaExperimentsClientOptions = {}) {
    this.apiKey =
      options.apiKey ?? process.env.LEMMA_API_KEY ?? "";
    this.baseUrl = options.baseUrl ?? process.env.LEMMA_API_URL ?? DEFAULT_BASE_URL;

    if (!this.apiKey) {
      throw new Error(
        "LemmaExperimentsClient: Missing API key. Set LEMMA_API_KEY environment variable or pass apiKey to the constructor."
      );
    }
  }

  async getTestCases(experimentId: string): Promise<TestCase[]> {
    const response = await fetch(
      `${this.baseUrl}/experiments/${experimentId}/test-cases`,
      {
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to get test cases: ${response.statusText}`);
    }

    return response.json() as Promise<TestCase[]>;
  }

  async recordResults(
    experimentId: string,
    strategyName: string,
    results: ExperimentResult[]
  ): Promise<void> {
    const response = await fetch(
      `${this.baseUrl}/experiments/${experimentId}/results`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify({
          strategyName,
          results,
        }),
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to record results: ${response.statusText}`);
    }
  }
}
