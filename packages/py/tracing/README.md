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

`wrap_agent` creates an OpenTelemetry span around your agent function and provides helpers for recording results.

```python
from uselemma_tracing import TraceContext, wrap_agent

def my_agent(ctx: TraceContext, user_message: str):
    result = do_work(user_message)
    ctx.record_generation_results({"response": result})
    return result

wrapped = wrap_agent("my-agent", my_agent, initial_state={"user_message": user_message})
result, run_id, span = wrapped()
```

## Environment Variables

| Variable           | Description           |
| ------------------ | --------------------- |
| `LEMMA_API_KEY`    | Your Lemma API key    |
| `LEMMA_PROJECT_ID` | Your Lemma project ID |

Both are required unless passed explicitly to `register_otel()`.

## Documentation

- [Tracing Overview](https://docs.uselemma.ai/tracing/overview) — concepts, API reference, and usage patterns

## License

MIT
