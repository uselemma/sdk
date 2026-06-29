# Lemma SDK

Official SDKs for sending AI agent traces to Lemma. The tracing packages capture
agent runs, spans, LLM generations, tool calls, inputs, outputs, timing, errors,
and OpenInference-compatible attributes, then send trace payloads
directly to Lemma over HTTP.

## Packages

| Package                                    | Language             | Current version | Path                  |
| ------------------------------------------ | -------------------- | --------------- | --------------------- |
| [`@uselemma/tracing`](packages/ts/tracing) | TypeScript / Node.js | `7.0.0`         | `packages/ts/tracing` |
| [`uselemma-tracing`](packages/py/tracing)  | Python               | `7.0.0`         | `packages/py/tracing` |

## Install

```bash
npm install @uselemma/tracing
```

```bash
pip install uselemma-tracing
```

Both SDKs read credentials from environment variables by default:

```bash
export LEMMA_API_KEY=...
export LEMMA_PROJECT_ID=...
```

The default API endpoint is `https://api.uselemma.ai/traces/ingest`. Override
the base URL with `baseUrl` / `base_url` when sending to a local or self-hosted
Lemma API router.

You can also pass configuration directly:

```typescript
const lemma = new Lemma({
  apiKey: "sk_...",
  projectId: "proj_...",
  baseUrl: "https://api.uselemma.ai",
});
```

```python
lemma = Lemma(
    api_key="sk_...",
    project_id="proj_...",
    base_url="https://api.uselemma.ai",
)
```

## TypeScript Quick Start

```typescript
import { Lemma } from "@uselemma/tracing";

const lemma = new Lemma();

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
      toolParameters: { query: "string" },
    });

    const response = await callModel(userMessage, docs);
    trace.recordGeneration({
      name: "draft-reply",
      input: response.messages,
      output: response.text,
      model: "gpt-4o",
      llmInputMessages: response.messages,
      llmInvocationParameters: { temperature: 0.2 },
    });

    return response.text;
  },
);
```

`lemma.trace(options, callback)` measures the trace duration from the callback
start to completion, sends the trace once the callback returns or throws, and
marks the trace as failed when the callback throws.

## Trace Handles

Use a trace handle when work is coordinated across helpers and you want to pass
IDs around explicitly.

```typescript
const trace = lemma.trace({
  name: "support-agent",
  input: userMessage,
  threadId: conversationId,
});

const retrieval = trace.startSpan({
  name: "retrieve-context",
  input: { query: userMessage },
});

const docs = await searchDocs(userMessage);
retrieval.recordTool({
  name: "search_docs",
  input: { query: userMessage },
  output: docs,
});
retrieval.end({ output: { count: docs.length } });

const generation = trace.startGeneration({
  name: "draft-reply",
  input: messages,
  model: "gpt-4o",
});
const response = await callModel(messages);
generation.end({
  output: response.text,
});

await trace.end({ output: response.text });
```

Handles know their start time when created and their end time when `.end()` is
called, so you usually do not pass `durationMs`. Pass `durationMs` only when
replaying historical work or when you need to override the measured duration
with a value from another timer.

## Recording By ID

When a helper cannot receive a trace object, pass IDs explicitly. Detached
operations require `traceId`; child operations also need `parentSpanId`.

```typescript
const trace = lemma.trace({ name: "support-agent", input: userMessage });

const retrieval = lemma.startSpan({
  traceId: trace.id,
  name: "retrieve-context",
  input: { query: userMessage },
});

lemma.recordTool({
  traceId: trace.id,
  parentSpanId: retrieval.id,
  name: "search_docs",
  output: docs,
});

retrieval.end({ output: { count: docs.length } });
await trace.end({ output: "Done" });
```

Calls that cannot attach safely warn and no-op instead of creating orphaned
observations.

## Vercel AI SDK

The TypeScript package supports both AI SDK v7 and v6.

AI SDK v7:

```typescript
import { generateText } from "ai";
import { vercelAI } from "@uselemma/tracing";

const lemmaTelemetry = vercelAI({
  apiKey: process.env.LEMMA_API_KEY,
  projectId: process.env.LEMMA_PROJECT_ID,
});

const result = await generateText({
  model,
  prompt: userMessage,
  telemetry: {
    functionId: "support-agent",
    integrations: [lemmaTelemetry],
  },
});

return result.text;
```

AI SDK v6:

```typescript
await generateText({
  model,
  prompt: userMessage,
  experimental_telemetry: {
    functionId: "support-agent",
    integrations: [lemmaTelemetry],
  },
});
```

The integration creates and closes the Lemma trace for the AI SDK run, extracts
the prompt/messages as trace input, and uses `functionId` as the agent name. You
can also set the agent name with `vercelAI({ agentName: "support-agent" })`.

For advanced cases, you can still pass a trace handle. The integration closes it
from the AI SDK terminal callback: `onEnd` in v7 and `onFinish` in v6. When you
use the callback form of `lemma.trace()`, your callback owns trace closure.

The integration records model calls as generations and tool executions as tool
spans. Use `vercelAI({ recordInputs: false, recordOutputs: false })` to avoid
sending prompts, tool inputs, tool outputs, and generated text.

## OpenAI Agents SDK

TypeScript:

```typescript
import { addTraceProcessor } from "@openai/agents";
import { openAIAgents } from "@uselemma/tracing";

addTraceProcessor(openAIAgents());
```

Python:

```bash
pip install "uselemma-tracing[openai-agents]" openai-agents
```

```python
from uselemma_tracing import instrument_openai_agents

instrument_openai_agents()
```

The processor sends one Lemma trace per OpenAI Agents trace. Generation spans
are recorded as Lemma generations, function spans are recorded as Lemma tool
spans, and parent IDs are preserved so tools stay nested under the generation
or agent span that called them.

Use `openAIAgents({ recordInputs: false, recordOutputs: false })` in
TypeScript or `openai_agents(record_inputs=False, record_outputs=False)` in
Python to avoid sending prompts, tool inputs, tool outputs, and generated text.

## LangChain and LangGraph

Both SDKs expose LangChain callback handlers. LangGraph uses the same callback
system, so `langGraph()` / `langgraph()` is an alias with a LangGraph-flavored
default trace name.

TypeScript:

```typescript
import { ChatOpenAI } from "@langchain/openai";
import { langChain } from "@uselemma/tracing";

const model = new ChatOpenAI({
  model: "gpt-4o",
  callbacks: [langChain({ agentName: "support-agent" })],
});

const response = await model.invoke(userMessage);
```

Python:

```bash
pip install "uselemma-tracing[langchain]" langchain-openai
```

```python
from langchain_openai import ChatOpenAI
from uselemma_tracing import langchain

model = ChatOpenAI(
    model="gpt-4o",
    callbacks=[langchain(agent_name="support-agent")],
)

response = model.invoke(user_message)
```

LangGraph:

```typescript
const result = await graph.invoke(
  { input: userMessage },
  { callbacks: [langGraph({ agentName: "support-graph" })] },
);
```

```python
result = graph.invoke(
    {"input": user_message},
    {"callbacks": [langgraph(agent_name="support-graph")]},
)
```

The integration creates one Lemma trace for the root chain/graph run, records
LLM calls as generations, tools as tool spans, retrievers as spans, and nested
chain/graph nodes as child spans.

## Python Quick Start

```python
from uselemma_tracing import Lemma

lemma = Lemma()

def run(trace):
    docs = search_docs(user_message)
    trace.record_tool(
        name="search_docs",
        input={"query": user_message},
        output=docs,
        tool_parameters={"query": "string"},
    )

    response = call_model(user_message, docs)
    trace.record_generation(
        name="draft-reply",
        input=response.messages,
        output=response.text,
        model="gpt-4o",
        llm_input_messages=response.messages,
        llm_invocation_parameters={"temperature": 0.2},
    )

    return response.text

answer = lemma.trace(
    "support-agent",
    run,
    input=user_message,
    thread_id=conversation_id,
    user_id=user.id,
)
```

Python also supports `async_trace()`, `start_span()`, `start_tool()`, and
`start_generation()` for measured live work.

## Supported Span Fields

Use first-class SDK options for common trace-contract fields:

- trace fields: `name`, `input`, `output`, `metadata`, `threadId` /
  `thread_id`, `userId` / `user_id`, `environment`, `durationMs` /
  `duration_ms`
- span fields: `name`, `type`, `input`, `output`, `metadata`, `attributes`,
  `startedAt` / `started_at`, `endedAt` / `ended_at`, `durationMs` /
  `duration_ms`, `status`, `error`
- generation fields: `model`, `llmModelName` / `llm_model_name`,
  `llmProvider` / `llm_provider`, `llmSystem` / `llm_system`,
  `llmInvocationParameters` / `llm_invocation_parameters`,
  `llmInputMessages` / `llm_input_messages`, `llmOutputMessages` /
  `llm_output_messages`, `llmTools` / `llm_tools`, and prompt template fields
- tool fields: `toolName` / `tool_name`, `toolDescription` /
  `tool_description`, `toolParameters` / `tool_parameters`
- embedding and reranker fields:
  `embeddingModelName` / `embedding_model_name`, `embeddingInvocationParameters` /
  `embedding_invocation_parameters`, `embeddingEmbeddings` /
  `embedding_embeddings`, `rerankerModelName` / `reranker_model_name`,
  `rerankerInputDocuments` / `reranker_input_documents`,
  `rerankerOutputDocuments` / `reranker_output_documents`

Use `attributes` for raw attributes that do not yet have a first-class SDK
option.

## Debug Mode

Debug mode logs trace lifecycle events, span starts, span completions, and send
results as they happen.

TypeScript:

```typescript
import { enableDebugMode } from "@uselemma/tracing";

enableDebugMode();
```

Python:

```python
from uselemma_tracing import enable_debug_mode

enable_debug_mode()
```

You can also set `LEMMA_DEBUG=true`. Use debug mode to confirm that spans are
being created in the order you expect, that parent IDs are attached, and that
the SDK is sending to the intended URL.

## Development

```bash
pnpm install
pnpm --filter @uselemma/tracing test
pnpm --filter @uselemma/tracing type-check
```

```bash
uv sync
cd packages/py/tracing
uv run pytest
```

## Documentation

- [TypeScript package README](packages/ts/tracing/README.md)
- [Python package README](packages/py/tracing/README.md)
- [Tracing Overview](https://docs.uselemma.ai/tracing/overview)
- [Trace Contract](https://docs.uselemma.ai/reference/trace-contract)
- [Vercel AI SDK Integration](https://docs.uselemma.ai/tracing/integrations/vercel-ai-sdk)

## License

MIT
