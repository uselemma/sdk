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

You can also enable experiment mode globally for the process:

```python
from uselemma_tracing import enable_experiment_mode

enable_experiment_mode()
```

### 2. Wrap your agent

`wrap_agent` creates a root OpenTelemetry span named `ai.agent.run` and records:
- `ai.agent.name`
- `lemma.run_id`
- `ai.agent.input`
- `lemma.is_experiment`

```python
from uselemma_tracing import TraceContext, wrap_agent

def my_agent(ctx: TraceContext, user_message: str):
    result = do_work(user_message)
    ctx.complete(result)
    return result

wrapped = wrap_agent("my-agent", my_agent, auto_end_root=True)
result, run_id, span = wrapped("hello")
```

## Export Behavior

- Spans are exported in run-specific batches keyed by `lemma.run_id`.
- A run batch is exported when its top-level `ai.agent.run` span ends.
- `force_flush()` exports remaining runs in separate batches per run.
- Spans with `instrumentation_scope.name == "next.js"` are excluded from export.

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
