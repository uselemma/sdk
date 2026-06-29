# @uselemma/tracing

HTTP tracing SDK for AI agents. No OpenTelemetry setup is required: the SDK sends completed trace payloads directly to the Lemma API.

## Installation

```bash
npm install @uselemma/tracing
```

## Quick Start

```typescript
import { Lemma } from "@uselemma/tracing";

const lemma = new Lemma({
  apiKey: process.env.LEMMA_API_KEY,
  projectId: process.env.LEMMA_PROJECT_ID,
});

const answer = await lemma.trace(
  {
    name: "support-agent",
    input: userMessage,
    threadId: conversationId,
    userId: user.id,
  },
  async (trace) => {
    const docs = await searchDocs(userMessage);
    trace.recordTool({
      name: "search_docs",
      input: { query: userMessage },
      output: docs,
    });

    const response = await callModel(userMessage, docs);
    trace.recordGeneration({
      name: "draft-reply",
      input: response.messages,
      output: response.text,
      model: "gpt-4o",
      usage: {
        inputTokens: response.usage.inputTokens,
        outputTokens: response.usage.outputTokens,
      },
    });

    return response.text;
  },
);
```

`trace()` creates one Lemma trace. The callback receives a context object; any child span, generation, or tool recorded through that context is attached to the trace.

## One-Off Events

Use one-off calls when the work already happened and you want to record it:

```typescript
trace.recordSpan({
  name: "rerank-results",
  input: { candidates: candidates.length },
  output: { kept: ranked.length },
});

trace.recordTool({
  name: "lookup_order",
  input: { orderId },
  output: order,
});

trace.recordGeneration({
  name: "answer",
  input: messages,
  output: text,
  model: "gpt-4o",
  llmInputMessages: [{ role: "user", content: userMessage }],
  llmInvocationParameters: { temperature: 0.2 },
});
```

Pass contract fields as native props such as `llmInputMessages`, `llmInvocationParameters`, `toolParameters`, and `retrievalDocuments`. Use `attributes` only when you need to send raw span attributes that do not yet have a native SDK prop.

## Live Spans

Use `startSpan()`, `startTool()`, or `startGeneration()` when you want the SDK to measure work from a handle and finish it later:

```typescript
const span = trace.startSpan({ name: "retrieve-context", input: query });
try {
  const docs = await retrieve(query);
  span.end({ output: docs, durationMs: 250 });
} catch (error) {
  span.end({ error });
  throw error;
}
```

```typescript
const tool = trace.startTool({ name: "search_docs", input: { query } });
const docs = await searchDocs(query);
tool.end({ output: docs, durationMs: 25 });

const generation = trace.startGeneration({
  name: "answer",
  input: messages,
  model: "gpt-4o",
});
const response = await callModel(messages);
generation.end({ output: response.text, durationMs: response.durationMs });
```

The SDK measures trace durations from timestamps. Pass `durationMs` on callback traces, spans, generations, tools, `span.end({ durationMs })`, or `trace.end({ durationMs })` when you already measured the work yourself. When child spans, generations, or tools omit `durationMs`, Lemma splits the parent's remaining unclaimed duration equally across siblings that also omitted duration.

You can also create a trace handle first and record work on it over time:

```typescript
const trace = lemma.trace({ name: "support-agent", input: userMessage });

const span = trace.startSpan("retrieve-context");
const docs = await retrieve(userMessage);
span.recordTool({
  name: "search_docs",
  input: { query: userMessage },
  output: docs,
  toolParameters: { query: "string" },
});
span.end({
  output: { count: docs.length },
  durationMs: 250,
  retrievalDocuments: docs.map((doc) => ({
    id: doc.id,
    content: doc.text,
    score: doc.score,
  })),
});

await trace.end({ output: "final answer", durationMs: 1234 });
```

## Vercel AI SDK

Pass `vercelAI()` to the AI SDK telemetry integrations option while the call runs inside a Lemma trace. AI SDK v7 uses `telemetry`; AI SDK v6 uses `experimental_telemetry`.

```typescript
import { generateText } from "ai";
import { Lemma, vercelAI } from "@uselemma/tracing";

const lemma = new Lemma();

const answer = await lemma.trace(
  { name: "support-agent", input: userMessage },
  async () => {
    const result = await generateText({
      model,
      prompt: userMessage,
      telemetry: {
        integrations: [vercelAI()],
      },
    });

    return result.text;
  },
);
```

For AI SDK v6, pass the same helper through `experimental_telemetry`:

```typescript
await generateText({
  model,
  prompt: userMessage,
  experimental_telemetry: {
    integrations: [vercelAI()],
  },
});
```

The integration records model calls as generations and tool executions as tool calls. Use `vercelAI({ recordInputs: false, recordOutputs: false })` to avoid sending prompts, tool inputs, tool outputs, or model output text.

When you pass a trace handle with `vercelAI({ trace })`, the integration ends it from the AI SDK terminal callback: `onEnd` in AI SDK v7 and `onFinish` in AI SDK v6. When you use the callback form of `lemma.trace()`, the callback still owns trace closure.

When a helper only has IDs, use the client-level methods:

```typescript
const trace = lemma.trace();

const span = lemma.startSpan({ traceId: trace.id });
lemma.recordTool({
  traceId: trace.id,
  parentSpanId: span.id,
  name: "tool call",
});

await trace.flush();
```

Detached handle calls require `traceId`. If a detached observation has a parent, pass `parentSpanId`; calls that cannot attach safely warn and no-op.

## Active Context

The SDK keeps the active trace in async context, so helpers deeper in your code can record without receiving the context explicitly:

```typescript
import { active } from "@uselemma/tracing";

export function recordSearch(docs: unknown[]) {
  active().recordTool({
    name: "search_docs",
    output: docs,
  });
}
```

## Configuration

| Option      | Environment variable | Default                   |
| ----------- | -------------------- | ------------------------- |
| `apiKey`    | `LEMMA_API_KEY`      | Required                  |
| `projectId` | `LEMMA_PROJECT_ID`   | Required                  |
| `baseUrl`   | none                 | `https://api.uselemma.ai` |

## Documentation

- [Quickstart](https://docs.uselemma.ai/getting-started/quickstart)
- [Trace contract](https://docs.uselemma.ai/reference/trace-contract)

## Examples

See [`examples/`](./examples) for complete callback tracing, trace handle, record-by-ID, and Vercel AI SDK v6/v7 examples.

## License

MIT
