# Tracing Module

OpenTelemetry-based tracing module for Lemma.

## Installation

```bash
npm install @uselemma/tracing
```

## Usage

### Basic Setup

```typescript
import { Tracer, TraceRunner } from "@uselemma/tracing";

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

  tracer.addLlmOutput("LLM response", "gpt-4", {
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
const tracedFunction = tracer.wrap(myFunction, "tool");

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
tracer.addLlmOutput(result.content);

// Method 2: Using startPrompt() (returns context object)
const promptCtx = tracer.startPrompt("translation", "Translate: {{ text }}", {
  text: "Hello",
});
// ... use promptCtx.renderedPrompt ...
tracer.addLlmOutput(result.content);
promptCtx.end(); // Manually end span
```

## Differences from Python Version

1. **Async Context**: Uses `AsyncLocalStorage` instead of Python's `contextvars`
2. **Template Engine**: Uses `nunjucks` instead of Jinja2
3. **Decorators**: The `observe()` decorator pattern is replaced with `wrap()` method
4. **Context Managers**: Python's `with` statements are replaced with `run()` callbacks

## API

### Tracer

- `wrap<T>(func: T, spanType: string): T` - Wrap a function for tracing
- `prompt(promptName: string, promptTemplate: string, inputVars: Record<string, unknown>): Promise<string>` - Create a prompt span and render template
- `startPrompt(...)`: Start a prompt span and return context object
- `addLlmOutput(output: string, model?: string, usage?: {...}): void` - Add LLM output to current prompt span
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
