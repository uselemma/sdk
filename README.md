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

`wrapAgent` creates an OpenTelemetry span around your agent function and provides helpers for recording results.

```typescript
import { wrapAgent } from "@uselemma/tracing";

const wrappedFn = wrapAgent(
  "my-agent",
  { initialState: { userMessage } },
  async ({ recordGenerationResults }) => {
    const result = await doWork(userMessage);
    recordGenerationResults({ response: result });
    return result;
  }
);

const { result, runId } = await wrappedFn();
```

## Environment Variables

| Variable | Description |
| --- | --- |
| `LEMMA_API_KEY` | Your Lemma API key |
| `LEMMA_PROJECT_ID` | Your Lemma project ID |

Both are required unless passed explicitly to `registerOTel()`.

## Documentation

- [Tracing Overview](https://docs.uselemma.ai/tracing/overview) — concepts, API reference, and usage patterns
- [Vercel AI SDK Integration](https://docs.uselemma.ai/tracing/integrations/vercel-ai-sdk) — framework setup, streaming, and examples

## License

MIT
