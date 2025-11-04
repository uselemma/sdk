# Tracing Module

OpenTelemetry-based tracing module for Lemma.

## Installation

```bash
npm install @uselemma/tracing
```

## Usage

### Basic Setup

```typescript
import { Tracer, TraceRunner, SpanType } from "@uselemma/tracing";

// Create a tracer
const tracer = new Tracer("my-service");

// Use TraceRunner for managing traces
const traceRunner = new TraceRunner(tracer, {
  "prompt-name": "override template here",
});

// Run code within tracing context
await traceRunner.run(async () => {
  // Your code here
  const renderedPrompt = await tracer.prompt(
    "prompt-name",
    "Hello {{ name }}!",
    { name: "World" }
  );

  // ... use renderedPrompt ...

  tracer.addLLMOutput("LLM response", "gpt-4", {
    prompt_tokens: 100,
    completion_tokens: 50,
    total_tokens: 150,
  });
});

// Get trace data
const traceData = await traceRunner.record();
console.log(traceData.trace_id);
console.log(traceData.spans);
```

### Function Tracing

```typescript
// Wrap a function for tracing
const tracedFunction = tracer.wrap(SpanType.TOOL, myFunction);

// Or use manually
const span = tracer.getCurrentSpan();
tracer.addMetadata("key", "value");
tracer.addEvent("event-name", { data: "value" });
```

### Prompt Tracing

```typescript
// Method 1: Using prompt() (returns rendered prompt)
const renderedPrompt = await tracer.prompt(
  "translation",
  "Translate: {{ text }}",
  { text: "Hello" }
);
// ... use renderedPrompt ...
tracer.addLLMOutput(result.content);

// Method 2: Using startPrompt() (returns context object)
const promptCtx = tracer.startPrompt("translation", "Translate: {{ text }}", {
  text: "Hello",
});
// ... use promptCtx.renderedPrompt ...
tracer.addLLMOutput(result.content);
promptCtx.end(); // Manually end span
```

## API

### SpanType

Enum for specifying span types:

- `SpanType.AGENT` - For agent operations
- `SpanType.NODE` - For node operations
- `SpanType.TOOL` - For tool operations

### Tracer

- `wrap<T>(spanType: SpanType, func: T): T` - Wrap a function for tracing
- `prompt(promptName: string, promptTemplate: string, inputVars: Record<string, unknown>): Promise<string>` - Create a prompt span and render template
- `startPrompt(...)`: Start a prompt span and return context object
- `addLLMOutput(output: string, model?: string, usage?: {...}): void` - Add LLM output to current prompt span
- `addMetadata(key: string, value: unknown): void` - Add metadata to current span
- `addEvent(eventName: string, attributes?: Record<string, unknown>): void` - Add event to current span
- `getTraceId(): string | undefined` - Get current trace ID
- `forceFlush(): Promise<void>` - Force flush all pending spans
- `getSpans(): ReadableSpan[]` - Get all collected spans
- `getSpansAsDicts(): SpanDict[]` - Get all collected spans as dictionaries

### TraceRunner

- `run<T>(callback: () => Promise<T> | T): Promise<T>` - Run callback within tracing context
- `record(): Promise<TraceData>` - Export spans and return trace data

### CandidatePromptManager

- `run<T>(candidatePrompts: Record<string, string> | null, callback: () => Promise<T> | T): Promise<T>` - Run callback with candidate prompts
- `getEffectiveTemplate(promptName: string, defaultTemplate: string): [string, boolean]` - Get effective template

### MemorySpanExporter

- `getSpans(): ReadableSpan[]` - Get all stored spans
- `getSpansAsDicts(): SpanDict[]` - Get all stored spans as dictionaries
- `clear(): void` - Clear stored spans
