# @uselemma/tracing

OpenTelemetry-based tracing for AI agents. Capture inputs, outputs, timing, token usage, and errors — then view everything in [Lemma](https://uselemma.ai).

## Installation

```bash
npm install @uselemma/tracing
```

## Quick Start

### 1. Register the tracer provider

`registerOTel` sets up a `NodeTracerProvider` that exports spans to Lemma over OTLP/proto. Call it once when your application starts.

```typescript
import { registerOTel } from "@uselemma/tracing";

registerOTel();
```

By default it reads `LEMMA_API_KEY` and `LEMMA_PROJECT_ID` from environment variables. You can also pass them explicitly:

```typescript
registerOTel({
  apiKey: "lma_...",
  projectId: "proj_...",
});
```

### 2. Wrap your agent

`wrapAgent` creates an OpenTelemetry span around your agent function and provides a `TraceContext` with helpers for recording results and errors.

```typescript
import { wrapAgent } from "@uselemma/tracing";

const callAgent = async (userMessage: string) => {
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
  return { result, runId };
};
```

## Framework Setup

### Next.js

Create an `instrumentation.ts` file in your project root. Next.js runs this automatically on startup:

```typescript
// instrumentation.ts
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { registerOTel } = await import("@uselemma/tracing");
    registerOTel();
  }
}
```

Enable the instrumentation hook in `next.config.js`:

```javascript
// next.config.js
module.exports = {
  experimental: {
    instrumentationHook: true,
  },
};
```

### Node.js

Import a setup file at the very top of your entry point:

```typescript
// tracer.ts
import { registerOTel } from "@uselemma/tracing";
registerOTel();
```

```typescript
// index.ts
import "./tracer"; // Must be first!
// ... rest of your imports
```

## API Reference

### `registerOTel(options?)`

Registers an OpenTelemetry tracer provider configured to send traces to Lemma. Returns the `NodeTracerProvider` instance.

#### `RegisterOTelOptions`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `apiKey` | `string` | `process.env.LEMMA_API_KEY` | Lemma API key |
| `projectId` | `string` | `process.env.LEMMA_PROJECT_ID` | Lemma project ID |
| `baseUrl` | `string` | `https://api.uselemma.ai` | Base URL for the Lemma API |

---

### `wrapAgent(name, options, fn)`

Wraps an agent function with OpenTelemetry tracing. Returns an async function that, when called, creates a span, executes `fn`, and returns `{ result, runId, span }`.

#### Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `name` | `string` | Agent name, used as the span name |
| `options` | `object` | Configuration (see below) |
| `fn` | `(ctx: TraceContext, ...args) => any` | Your agent logic |

#### Options

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `initialState` | `any` | — | Inputs to record on the trace |
| `endOnExit` | `boolean` | `true` | Auto-end the span when `fn` returns |
| `isExperiment` | `boolean` | `false` | Tag this run as an experiment |

#### Return value

| Field | Type | Description |
| --- | --- | --- |
| `result` | `any` | The return value of your agent function |
| `runId` | `string` | Unique identifier for this trace |
| `span` | `Span` | The underlying OpenTelemetry span |

---

### `TraceContext`

Passed as the first argument to your agent function.

| Field | Type | Description |
| --- | --- | --- |
| `span` | `Span` | The OpenTelemetry span for custom instrumentation |
| `runId` | `string` | Unique run identifier |
| `onComplete(result)` | `(result: unknown) => void` | Records output and ends the span |
| `onError(error)` | `(error: unknown) => void` | Records the error and ends the span |
| `recordGenerationResults(results)` | `(results: Record<string, string>) => void` | Attaches generation outputs (e.g. `{ response: "..." }`) to the span |

> When `endOnExit` is `true` (the default), the span ends automatically after your function returns. When `endOnExit` is `false`, you must call `onComplete` or `onError` yourself to end the span.

## Streaming

For streaming responses, set `endOnExit: false` and manually signal when the trace ends:

```typescript
import { wrapAgent } from "@uselemma/tracing";
import { streamText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";

const callAgent = async (userMessage: string) => {
  const wrappedFn = wrapAgent(
    "my-agent",
    { initialState: { userMessage }, endOnExit: false },
    async ({ onComplete, onError, recordGenerationResults }) => {
      return streamText({
        model: anthropic("claude-sonnet-4"),
        messages: [{ role: "user", content: userMessage }],
        experimental_telemetry: { isEnabled: true },
        onFinish: (result) => {
          recordGenerationResults({ response: result.text });
          onComplete(result);
        },
        onError,
      });
    }
  );

  const { result, runId } = await wrappedFn();
  return { result, runId };
};
```

## Environment Variables

| Variable | Description |
| --- | --- |
| `LEMMA_API_KEY` | Your Lemma API key |
| `LEMMA_PROJECT_ID` | Your Lemma project ID |

Both are required unless passed explicitly to `registerOTel()`. You can find these in your [Lemma project settings](https://uselemma.ai).

## License

MIT
