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

You can also enable experiment mode globally for the process:

```typescript
import { enableExperimentMode } from "@uselemma/tracing";

enableExperimentMode();
```

### 2. Wrap your agent

`wrapAgent` creates a root OpenTelemetry span named `ai.agent.run` and records:
- `ai.agent.name`
- `lemma.run_id`
- `ai.agent.input`
- `lemma.is_experiment`

```typescript
import { wrapAgent } from "@uselemma/tracing";

const wrappedFn = wrapAgent(
  "my-agent",
  async ({ onComplete }) => {
    const result = await doWork(userMessage);
    onComplete(result);
    return result;
  },
  { autoEndRoot: true },
);

const { result, runId } = await wrappedFn();
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

- [Tracing Overview](https://docs.uselemma.ai/tracing/overview) — concepts, API reference, and usage patterns
- [Vercel AI SDK Integration](https://docs.uselemma.ai/tracing/integrations/vercel-ai-sdk) — framework setup, streaming, and examples

## License

MIT
