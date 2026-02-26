import cliProgress from "cli-progress";
import { enableExperimentMode, registerOTel } from "@uselemma/tracing";
import { LemmaExperimentsClient } from "./client";
import type {
  ExperimentResult,
  ExperimentSummary,
  LemmaExperimentRunnerOptions,
  RunExperimentOptions,
  TestCase,
} from "./types";

export class LemmaExperimentRunner {
  private readonly client: LemmaExperimentsClient;
  private readonly tracerProvider: { forceFlush(): Promise<void> };

  constructor(options: LemmaExperimentRunnerOptions = {}) {
    this.tracerProvider = registerOTel({
      apiKey: options.apiKey ?? process.env.LEMMA_API_KEY,
      projectId: options.projectId ?? process.env.LEMMA_PROJECT_ID,
      baseUrl: options.baseUrl,
    });
    enableExperimentMode();

    this.client = new LemmaExperimentsClient({
      apiKey: options.apiKey ?? process.env.LEMMA_API_KEY,
      baseUrl: options.baseUrl ?? process.env.LEMMA_API_URL,
    });
  }

  async runExperiment<TInput = Record<string, unknown>>(
    options: RunExperimentOptions<TInput>
  ): Promise<ExperimentSummary> {
    const {
      experimentId,
      strategyName,
      agent,
      concurrency,
      progress = true,
    } = options;

    const testCases = await this.client.getTestCases(experimentId);
    const total = testCases.length;

    const results: ExperimentResult[] = [];
    let completed = 0;

    const maybeIncrement = () => {
      completed++;
      if (progress && bar) {
        bar.update(completed);
      }
    };

    let bar: cliProgress.SingleBar | null = null;
    if (progress && total > 0) {
      bar = new cliProgress.SingleBar(
        {},
        cliProgress.Presets.shades_classic
      );
      bar.start(total, 0);
    }

    const runOne = async (testCase: TestCase<TInput>): Promise<ExperimentResult | null> => {
      try {
        const { runId } = await agent(testCase.inputData as TInput);
        const result: ExperimentResult = { runId, testCaseId: testCase.id };
        results.push(result);
        return result;
      } catch {
        return null;
      } finally {
        maybeIncrement();
      }
    };

    const cases = testCases as TestCase<TInput>[];
    if (concurrency != null && concurrency > 0) {
      await this.runWithConcurrency(cases, runOne, concurrency);
    } else {
      await Promise.all(cases.map(runOne));
    }

    if (bar) {
      bar.stop();
    }

    await this.tracerProvider.forceFlush();
    await this.client.recordResults(experimentId, strategyName, results);

    return { successful: results.length, total };
  }

  private async runWithConcurrency<T>(
    items: T[],
    fn: (item: T) => Promise<unknown>,
    concurrency: number
  ): Promise<void> {
    let index = 0;
    async function worker(): Promise<void> {
      while (true) {
        const i = index++;
        if (i >= items.length) break;
        await fn(items[i]);
      }
    }
    await Promise.all(
      Array.from(
        { length: Math.min(concurrency, items.length) },
        () => worker()
      )
    );
  }
}
