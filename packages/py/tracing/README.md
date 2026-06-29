# uselemma-tracing

HTTP tracing SDK for AI agents. The primary API sends completed trace payloads directly to Lemma.

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
        duration_ms=25,
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
        duration_ms=40,
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
    duration_ms=1234,
)
```

## Live Spans

```python
def run(trace):
    span = trace.start_span(name="retrieve-context", input=query)
    try:
        docs = retrieve(query)
        span.end(
            output=docs,
            duration_ms=250,
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

Pass `duration_ms` when you already measured a child span, generation, or tool call. When child records omit `duration_ms`, Lemma splits the parent's remaining unclaimed duration equally across siblings that also omitted duration.

## Configuration

| Option | Environment variable | Default |
| --- | --- | --- |
| `api_key` | `LEMMA_API_KEY` | Required |
| `project_id` | `LEMMA_PROJECT_ID` | Required |
| `base_url` | none | `https://api.uselemma.ai` |

## License

MIT
