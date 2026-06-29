import { active, type TraceContext } from "./client";

type MaybePromise<T> = T | PromiseLike<T>;

type VercelAIModelCallStartEvent = {
  callId: string;
  provider: string;
  modelId: string;
  messages?: unknown[];
  tools?: ReadonlyArray<Record<string, unknown>>;
};

type VercelAIModelCallEndEvent = {
  callId: string;
  provider: string;
  modelId: string;
  usage: {
    inputTokens?: number;
    outputTokens?: number;
  };
  content: ReadonlyArray<unknown>;
  performance: {
    responseTimeMs?: number;
  };
};

type VercelAIEndEvent = {
  text?: string;
  content?: ReadonlyArray<unknown>;
};

type VercelAIToolExecutionEndEvent = {
  toolCall: {
    toolName: string;
    input?: unknown;
  };
  toolExecutionMs?: number;
  toolOutput:
    | {
        type: "tool-result";
        output?: unknown;
      }
    | {
        type: "tool-error";
        error?: unknown;
      };
};

type VercelAIV6ModelInfo = {
  provider: string;
  modelId: string;
};

type VercelAIV6StepStartEvent = {
  stepNumber: number;
  model: VercelAIV6ModelInfo;
  messages?: unknown[];
  tools?: unknown;
};

type VercelAIV6StepFinishEvent = {
  stepNumber: number;
  model: VercelAIV6ModelInfo;
  text?: string;
  content?: ReadonlyArray<unknown>;
  usage?: {
    inputTokens?: number;
    outputTokens?: number;
  };
};

type VercelAIV6StartEvent = {
  model: VercelAIV6ModelInfo;
  prompt?: string | unknown[];
  messages?: unknown[];
  tools?: unknown;
};

type VercelAIV6FinishEvent = {
  model: VercelAIV6ModelInfo;
  text?: string;
  content?: ReadonlyArray<unknown>;
  totalUsage?: {
    inputTokens?: number;
    outputTokens?: number;
  };
  usage?: {
    inputTokens?: number;
    outputTokens?: number;
  };
};

type VercelAIV6ToolCallFinishEvent = {
  toolCall: {
    toolName: string;
    input?: unknown;
  };
  durationMs?: number;
} & (
  | {
      success: true;
      output?: unknown;
      error?: never;
    }
  | {
      success: false;
      output?: never;
      error?: unknown;
    }
);

export type VercelAITelemetryIntegration = {
  onLanguageModelCallStart?: (
    event: VercelAIModelCallStartEvent,
  ) => MaybePromise<void>;
  onLanguageModelCallEnd?: (
    event: VercelAIModelCallEndEvent,
  ) => MaybePromise<void>;
  onToolExecutionEnd?: (
    event: VercelAIToolExecutionEndEvent,
  ) => MaybePromise<void>;
  onStart?: (event: VercelAIV6StartEvent) => MaybePromise<void>;
  onStepStart?: (event: VercelAIV6StepStartEvent) => MaybePromise<void>;
  onStepFinish?: (event: VercelAIV6StepFinishEvent) => MaybePromise<void>;
  onFinish?: (event: VercelAIV6FinishEvent) => MaybePromise<void>;
  onEnd?: (event: VercelAIEndEvent) => MaybePromise<void>;
  onToolCallFinish?: (
    event: VercelAIV6ToolCallFinishEvent,
  ) => MaybePromise<void>;
};

export type VercelAIIntegrationOptions = {
  trace?: TraceContext;
  generationName?:
    | string
    | ((
        event:
          | VercelAIModelCallEndEvent
          | VercelAIV6StepFinishEvent
          | VercelAIV6FinishEvent,
      ) => string);
  toolName?:
    | string
    | ((
        event: VercelAIToolExecutionEndEvent | VercelAIV6ToolCallFinishEvent,
      ) => string);
  metadata?: Record<string, unknown>;
  recordInputs?: boolean;
  recordOutputs?: boolean;
};

type StoredModelCall = {
  event: VercelAIModelCallStartEvent;
  startedAt: Date;
};

type StoredV6Step = {
  event: VercelAIV6StepStartEvent | VercelAIV6StartEvent;
  startedAt: Date;
};

function getTrace(trace: TraceContext | undefined): TraceContext | undefined {
  if (trace) return trace;
  try {
    return active();
  } catch {
    console.warn(
      "@uselemma/tracing: vercelAI() telemetry received an event outside lemma.trace(); event ignored",
    );
    return undefined;
  }
}

function stringifyContent(content: ReadonlyArray<unknown>): string {
  const text = content
    .map((part) => {
      if (!part || typeof part !== "object") return "";
      if ((part as { type?: unknown }).type !== "text") return "";
      return String((part as { text?: unknown }).text ?? "");
    })
    .join("");
  if (text) return text;
  return JSON.stringify(content);
}

function toolOutput(
  event: VercelAIToolExecutionEndEvent,
  recordOutputs: boolean,
) {
  if (!recordOutputs) {
    return event.toolOutput.type === "tool-error"
      ? { status: "ERROR" as const }
      : {};
  }
  if (event.toolOutput.type === "tool-result") {
    return { output: event.toolOutput.output };
  }
  return {
    error: event.toolOutput.error,
    status: "ERROR" as const,
  };
}

function v6ToolOutput(
  event: VercelAIV6ToolCallFinishEvent,
  recordOutputs: boolean,
) {
  if (!recordOutputs) {
    return event.success ? {} : { status: "ERROR" as const };
  }
  if (event.success) {
    return { output: event.output };
  }
  return {
    error: event.error,
    status: "ERROR" as const,
  };
}

function v6Input(event: VercelAIV6StepStartEvent | VercelAIV6StartEvent) {
  if ("messages" in event && event.messages) return event.messages;
  return "prompt" in event ? event.prompt : undefined;
}

function v6InputMessages(
  event: VercelAIV6StepStartEvent | VercelAIV6StartEvent,
) {
  const input = v6Input(event);
  return Array.isArray(input) ? input : undefined;
}

function v6Output(event: VercelAIV6StepFinishEvent | VercelAIV6FinishEvent) {
  if (typeof event.text === "string") return event.text;
  if (event.content) return stringifyContent(event.content);
  return undefined;
}

export function vercelAI(
  options: VercelAIIntegrationOptions = {},
): VercelAITelemetryIntegration {
  const modelCalls = new Map<string, StoredModelCall>();
  const v6Steps = new Map<number, StoredV6Step>();
  const v6Starts: StoredV6Step[] = [];
  let recordedV6Step = false;
  let endedExplicitTrace = false;

  function endOutput(event: VercelAIEndEvent | VercelAIV6FinishEvent) {
    if (typeof event.text === "string") return event.text;
    if (event.content) return stringifyContent(event.content);
    return undefined;
  }

  async function endExplicitTrace(
    event: VercelAIEndEvent | VercelAIV6FinishEvent,
  ) {
    if (endedExplicitTrace) return;
    const trace = options.trace as
      | (TraceContext & {
          end?: (outputOrOptions?: unknown) => MaybePromise<void>;
        })
      | undefined;
    if (typeof trace?.end !== "function") return;

    endedExplicitTrace = true;
    const output = endOutput(event);
    if (options.recordOutputs === false || output === undefined) {
      await trace.end();
      return;
    }
    await trace.end({ output });
  }

  function recordV6Generation(
    event: VercelAIV6StepFinishEvent | VercelAIV6FinishEvent,
    stored: StoredV6Step | undefined,
  ) {
    const trace = getTrace(options.trace);
    if (!trace) return;

    const startedAt = stored?.startedAt ?? new Date();
    const endedAt = new Date();
    const name =
      typeof options.generationName === "function"
        ? options.generationName(event)
        : (options.generationName ?? "vercel-ai-generation");
    const usage = "totalUsage" in event ? event.totalUsage : event.usage;
    const output = v6Output(event);

    trace.recordGeneration({
      name,
      input:
        options.recordInputs === false
          ? undefined
          : stored?.event && v6Input(stored.event),
      output: options.recordOutputs === false ? undefined : output,
      metadata: options.metadata,
      model: event.model.modelId,
      usage: {
        inputTokens: usage?.inputTokens,
        outputTokens: usage?.outputTokens,
      },
      startedAt,
      endedAt,
      llmProvider: event.model.provider,
      llmInputMessages:
        options.recordInputs === false || !stored?.event
          ? undefined
          : v6InputMessages(stored.event),
      llmOutputMessages:
        options.recordOutputs === false || output === undefined
          ? undefined
          : [{ role: "assistant", content: output }],
      llmTools: stored?.event.tools,
    });
  }

  return {
    onLanguageModelCallStart(event) {
      modelCalls.set(event.callId, { event, startedAt: new Date() });
    },

    onLanguageModelCallEnd(event) {
      const trace = getTrace(options.trace);
      if (!trace) return;

      const stored = modelCalls.get(event.callId);
      modelCalls.delete(event.callId);

      const startedAt = stored?.startedAt ?? new Date();
      const endedAt = new Date();
      const name =
        typeof options.generationName === "function"
          ? options.generationName(event)
          : (options.generationName ?? "vercel-ai-generation");

      trace.recordGeneration({
        name,
        input:
          options.recordInputs === false ? undefined : stored?.event.messages,
        output:
          options.recordOutputs === false
            ? undefined
            : stringifyContent(event.content),
        metadata: options.metadata,
        model: event.modelId,
        usage: {
          inputTokens: event.usage.inputTokens,
          outputTokens: event.usage.outputTokens,
        },
        startedAt,
        endedAt,
        durationMs: event.performance.responseTimeMs,
        llmProvider: event.provider,
        llmInputMessages:
          options.recordInputs === false ? undefined : stored?.event.messages,
        llmOutputMessages:
          options.recordOutputs === false
            ? undefined
            : [{ role: "assistant", content: stringifyContent(event.content) }],
        llmTools: stored?.event.tools,
      });
    },

    onToolExecutionEnd(event) {
      const trace = getTrace(options.trace);
      if (!trace) return;

      const name =
        typeof options.toolName === "function"
          ? options.toolName(event)
          : (options.toolName ?? event.toolCall.toolName);

      trace.recordTool({
        name,
        input:
          options.recordInputs === false ? undefined : event.toolCall.input,
        metadata: options.metadata,
        durationMs: event.toolExecutionMs,
        ...toolOutput(event, options.recordOutputs !== false),
      });
    },

    onStart(event) {
      recordedV6Step = false;
      v6Starts.push({ event, startedAt: new Date() });
    },

    onStepStart(event) {
      v6Steps.set(event.stepNumber, { event, startedAt: new Date() });
    },

    onStepFinish(event) {
      recordedV6Step = true;
      const stored = v6Steps.get(event.stepNumber);
      v6Steps.delete(event.stepNumber);
      recordV6Generation(event, stored);
    },

    async onFinish(event) {
      if (recordedV6Step) {
        v6Starts.shift();
        recordedV6Step = false;
        await endExplicitTrace(event);
        return;
      }
      recordV6Generation(event, v6Starts.shift());
      await endExplicitTrace(event);
    },

    async onEnd(event) {
      await endExplicitTrace(event);
    },

    onToolCallFinish(event) {
      const trace = getTrace(options.trace);
      if (!trace) return;

      const name =
        typeof options.toolName === "function"
          ? options.toolName(event)
          : (options.toolName ?? event.toolCall.toolName);

      trace.recordTool({
        name,
        input:
          options.recordInputs === false ? undefined : event.toolCall.input,
        metadata: options.metadata,
        durationMs: event.durationMs,
        ...v6ToolOutput(event, options.recordOutputs !== false),
      });
    },
  };
}

export type LemmaVercelAIIntegrationOptions = VercelAIIntegrationOptions;
