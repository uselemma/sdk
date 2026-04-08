# @uselemma/tracing

OpenTelemetry-based tracing for AI agents. Capture inputs, outputs, timing, token usage, and errors — then view everything in [Lemma](https://uselemma.ai).

## Installation

```bash
npm install @uselemma/tracing
```

## Quick Start

### 1. Register the tracer provider

Call `registerOTel` once when your application starts. It reads `LEMMA_API_KEY` and `LEMMA_PROJECT_ID` from environment variables by default.

```typescript
import { registerOTel } from "@uselemma/tracing";

registerOTel();
```

### 2. Wrap your agent

`agent` creates a root OpenTelemetry span named `ai.agent.run`. Return a value from the wrapped function — the wrapper auto-captures it as `ai.agent.output` and closes the span automatically.

```typescript
import { agent } from "@uselemma/tracing";

const myAgent = agent(
  "my-agent",
  async (input: { userMessage: string }) => {
    const result = await doWork(input.userMessage);
    return result; // wrapper auto-captures output and closes the span
  },
);

const { result, runId } = await myAgent(
  { userMessage: "hello" },
  { threadId: "thread_123" }, // optional: link multi-turn runs
);
```

### 3. Add child spans (optional)

Use the typed helpers to add spans for internal functions:

```typescript
import { agent, tool, retrieval, llm, trace } from "@uselemma/tracing";

const search = retrieval("vector-search", async (query: string) => {
  return vectorDB.search(query, { topK: 5 });
});

const lookupOrder = tool("lookup-order", async (orderId: string) => {
  return db.orders.findById(orderId);
});

const agent = agent("rag-agent", async (input: string) => {
  const docs = await search(input);   // retrieval.vector-search span
  const context = docs.join("\n");
  return generateAnswer(context, input);
});
```

## Export Behavior

- Spans are exported in run-specific batches keyed by `lemma.run_id`.
- A run batch is exported when its top-level `ai.agent.run` span ends.
- `forceFlush()` exports remaining runs in separate batches per run.
- Spans with `instrumentationScope.name === "next.js"` are excluded from export.

## Environment Variables

| Variable           | Description           |
| ------------------ | --------------------- |
| `LEMMA_API_KEY`    | Your Lemma API key    |
| `LEMMA_PROJECT_ID` | Your Lemma project ID |

Both are required unless passed explicitly to `registerOTel()`.

## Documentation

- [Quickstart](https://docs.uselemma.ai/getting-started/quickstart) — first trace in 2 minutes
- [Tracing Overview](https://docs.uselemma.ai/tracing/overview) — concepts, API reference, and usage patterns
- [Vercel AI SDK](https://docs.uselemma.ai/integrations/vercel-ai-sdk) — framework setup, streaming, and examples

## License

MIT
