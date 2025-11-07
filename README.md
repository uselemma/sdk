# @uselemma/tracing

Utilities for OpenTelemetry-based tracing and prompt management.

## Installation

```bash
npm install @uselemma/tracing
```

## Components

### MemorySpanExporter

A custom OpenTelemetry span exporter that stores spans in memory for programmatic access. Useful for testing, debugging, or capturing trace data for custom processing.

#### Usage

```typescript
import { NodeSDK } from "@opentelemetry/sdk-node";
import { SimpleSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { MemorySpanExporter } from "@uselemma/tracing";

// Create and configure the exporter
const memoryExporter = new MemorySpanExporter();

const sdk = new NodeSDK({
  spanProcessors: [new SimpleSpanProcessor(memoryExporter)],
});

sdk.start();

// Later, retrieve spans
const allSpans = memoryExporter.getSpans();
const spansAsDicts = memoryExporter.getSpansAsDicts();
const traceSpans = memoryExporter.getSpansByTraceId("your-trace-id");

// Clear memory when needed
memoryExporter.clear();
```

#### Methods

- **`getSpans(): ReadableSpan[]`** - Get all stored spans as OpenTelemetry ReadableSpan objects
- **`getSpansAsDicts(): SpanDict[]`** - Get all stored spans as formatted dictionaries
- **`getSpansByTraceId(traceId: string): SpanDict[]`** - Get all spans for a specific trace ID
- **`clear(): void`** - Clear all stored spans from memory
- **`export(spans: ReadableSpan[]): Promise<{ code: ExportResultCode }>`** - Export spans (called automatically by OpenTelemetry)
- **`shutdown(): Promise<void>`** - Shutdown the exporter
- **`forceFlush(): Promise<void>`** - Force flush pending spans

### CandidatePromptManager

Manages prompt template overrides using AsyncLocalStorage for context-local state. Useful for A/B testing or evaluating different prompt variations.

#### Usage

```typescript
import { CandidatePromptManager } from "@uselemma/tracing";

const promptManager = new CandidatePromptManager();

// Run code with prompt overrides
await promptManager.run(
  {
    greeting: "Hello {{ name }}, welcome!",
    farewell: "Goodbye {{ name }}!",
  },
  async () => {
    // Within this context, candidate prompts will be used
    const [template, wasOverridden] = promptManager.getEffectiveTemplate(
      "greeting",
      "Hi {{ name }}" // default template
    );

    console.log(template); // "Hello {{ name }}, welcome!"
    console.log(wasOverridden); // true
  }
);
```

#### Methods

- **`run<T>(candidatePrompts: Record<string, string> | null, callback: () => Promise<T> | T): Promise<T>`**  
  Run a callback with candidate prompts set in the async context
- **`getEffectiveTemplate(promptName: string, defaultTemplate: string): [string, boolean]`**  
  Get the effective template, applying candidate override if present. Returns `[template, wasOverridden]`
- **`annotateSpan(span: { setAttribute: (key: string, value: unknown) => void }): void`**  
  Annotate an OpenTelemetry span with candidate prompt metadata

## Example: Dual Processor Setup

Use `MemorySpanExporter` alongside other exporters to both send traces to your backend and capture them locally:

```typescript
import { NodeSDK } from "@opentelemetry/sdk-node";
import { SimpleSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { MemorySpanExporter } from "@uselemma/tracing";
import { OtherSpanProcessor } from "your-backend";

export const memoryExporter = new MemorySpanExporter();

const sdk = new NodeSDK({
  spanProcessors: [
    new OtherSpanProcessor(), // Send to your backend
    new SimpleSpanProcessor(memoryExporter), // Store in memory for local access
  ],
});

sdk.start();

// In your application code
import { memoryExporter } from "./instrumentation";

function myTracedFunction() {
  // ... your code ...

  // Access spans programmatically
  const allSpans = memoryExporter.getSpansAsDicts();
  const myTrace = memoryExporter.getSpansByTraceId(currentTraceId);
}
```

## License

MIT
