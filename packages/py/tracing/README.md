# uselemma-tracing

OpenTelemetry-based tracing for AI agents. Capture inputs, outputs, timing, token usage, and errors — then view everything in [Lemma](https://uselemma.ai).

## Installation

```bash
pip install uselemma-tracing
```

## Quick Start

### 1. Register the tracer provider

Call `register_otel` once when your application starts. It reads `LEMMA_API_KEY` and `LEMMA_PROJECT_ID` from environment variables by default.

```python
from uselemma_tracing import register_otel

register_otel()
```

### 2. Wrap your agent

`agent` creates a root OpenTelemetry span named `ai.agent.run`. Return a value from the wrapped function — the wrapper auto-captures it as `ai.agent.output` and closes the span automatically. The result is a `TraceResult` with named fields — and also supports tuple unpacking for backward compatibility.

```python
from uselemma_tracing import TraceContext, agent

async def run_agent(user_message: str, ctx: TraceContext) -> str:
    result = await do_work(user_message)
    return result  # wrapper auto-captures output and closes the span

myAgent = agent("my-agent", run_agent)

# Named access (recommended)
res = await myAgent("hello", {"thread_id": "thread_123"})
print(res.result, res.run_id)

# Tuple unpacking also works
result, run_id, span = await myAgent("hello")
```

### 3. Add typed decorators (optional)

Use `@tool`, `@retrieval`, `@llm`, and `@trace` to add child spans to internal functions:

```python
from uselemma_tracing import agent, tool, retrieval, TraceContext

@retrieval("vector-search")
async def search(query: str) -> list:
    return await vector_db.search(query, top_k=5)

@tool("lookup-order")
async def lookup_order(order_id: str) -> dict:
    return await db.orders.get(order_id)

async def run_agent(user_message: str, ctx: TraceContext) -> str:
    docs = await search(user_message)      # retrieval.vector-search span
    context = "\n".join(docs)
    return await generate_answer(context, user_message)

agent = agent("rag-agent", run_agent)
```

### 4. Context manager (no function extraction needed)

```python
from uselemma_tracing import agent

async def handle_request(user_message: str) -> str:
    async with agent("my-agent", input=user_message) as run:
        response = await call_llm(user_message)
        run.complete(response)  # sets ai.agent.output; span closes on block exit
    return response
```

## Export Behavior

- Spans are exported in run-specific batches keyed by `lemma.run_id`.
- A run batch is exported when its top-level `ai.agent.run` span ends.
- `force_flush()` exports remaining runs in separate batches per run.

## Environment Variables

| Variable           | Description           |
| ------------------ | --------------------- |
| `LEMMA_API_KEY`    | Your Lemma API key    |
| `LEMMA_PROJECT_ID` | Your Lemma project ID |

Both are required unless passed explicitly to `register_otel()`.

## Documentation

- [Quickstart](https://docs.uselemma.ai/getting-started/quickstart) — first trace in 2 minutes
- [Tracing Overview](https://docs.uselemma.ai/tracing/overview) — concepts, API reference, and usage patterns
- [OpenAI SDK (Python)](https://docs.uselemma.ai/integrations/openai-sdk-python)
- [Anthropic SDK (Python)](https://docs.uselemma.ai/integrations/anthropic-sdk-python)
- [LangChain](https://docs.uselemma.ai/integrations/langchain)

## License

MIT
