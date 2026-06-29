# uselemma-tracing

HTTP tracing SDK for AI agents. The primary API sends trace payloads directly to Lemma over HTTP.

## Installation

```bash
pip install uselemma-tracing
```

## Quick Start

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
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        llm_input_messages=[{"role": "user", "content": user_message}],
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

`lemma.trace()` measures the trace from callback start to completion. Use
`async_trace()` for async callbacks.

## Live Spans

```python
def run(trace):
    span = trace.start_span(name="retrieve-context", input=query)
    try:
        docs = retrieve(query)
        span.end(
            output=docs,
            retrieval_documents=[
                {"id": doc.id, "content": doc.text, "score": doc.score}
                for doc in docs
            ],
        )
        return docs
    except Exception as error:
        span.end(status="ERROR", error=error)
        raise
```

Live handles know their start time when created and their end time when
`.end()` is called, so you usually do not pass `duration_ms`. Pass
`duration_ms` only when replaying historical work or overriding the measured
duration with a value from another timer.

For one-off records where you already measured the work, pass `duration_ms` on
the record call:

```python
trace.record_generation(
    name="answer",
    output=text,
    model="gpt-4o",
    duration_ms=measured_model_ms,
)
```

The same handle pattern is available for tool calls and generations:

```python
tool = trace.start_tool(name="search_docs", input={"query": query})
docs = search_docs(query)
tool.end(output=docs)

generation = trace.start_generation(name="answer", input=messages)
response = call_model(messages)
generation.end(output=response.text)
```

## Supported Contract Fields

Use native SDK keyword arguments for OpenInference-style fields:

- LLM: `llm_model_name`, `llm_provider`, `llm_system`,
  `llm_invocation_parameters`, `llm_input_messages`, `llm_output_messages`,
  `llm_tools`, token counts, and prompt template fields
- tools: `tool_description`, `tool_parameters`
- retrieval: `retrieval_documents`
- embeddings and rerankers: `embedding_model_name`,
  `embedding_invocation_parameters`, `embedding_embeddings`,
  `reranker_model_name`, `reranker_input_documents`,
  `reranker_output_documents`

Use `attributes` for raw attributes that do not yet have a native SDK keyword.

## Configuration

| Option | Environment variable | Default |
| --- | --- | --- |
| `api_key` | `LEMMA_API_KEY` | Required |
| `project_id` | `LEMMA_PROJECT_ID` | Required |
| `base_url` | none | `https://api.uselemma.ai` |

The SDK sends to `{base_url}/traces/ingest`.

You can pass configuration directly to the constructor instead of using
environment variables:

```python
lemma = Lemma(
    api_key="sk_...",
    project_id="proj_...",
    base_url="https://api.uselemma.ai",
)
```

## Debug Mode

Debug mode logs trace starts, span starts, span completions, send attempts, and
send results as they happen:

```python
from uselemma_tracing import enable_debug_mode

enable_debug_mode()
```

You can also set `LEMMA_DEBUG=true`. Use this when validating that spans are
created in the expected order and the SDK is sending to the intended URL.

## License

MIT
