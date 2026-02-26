export interface TestCase<TInput = Record<string, unknown>> {
  id: string;
  inputData: TInput;
}

export interface ExperimentResult {
  runId: string;
  testCaseId: string;
}

export interface LemmaExperimentRunnerOptions {
  apiKey?: string;
  projectId?: string;
  baseUrl?: string;
}

export interface RunExperimentOptions<TInput = Record<string, unknown>> {
  experimentId: string;
  strategyName: string;
  agent: (input: TInput) => Promise<{ runId: string }>;
  concurrency?: number;
  progress?: boolean;
}

export interface ExperimentSummary {
  successful: number;
  total: number;
}
