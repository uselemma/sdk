# uselemma-experiments

Run experiments against Lemma test cases — fetch cases, run your agent, record results and traces.

## Installation

```bash
pip install uselemma-experiments
```

For local development in the SDK monorepo, use `uv` (workspaces are already configured at the repo root):

```bash
uv sync
```

## Quick Start

```python
from uselemma_experiments import LemmaExperimentRunner

runner = LemmaExperimentRunner()

await runner.run_experiment(
    experiment_id="exp_abc123",
    strategy_name="baseline",
    agent=lambda input: my_agent(input),
)
```

## Environment Variables

| Variable           | Description           |
| ------------------ | --------------------- |
| `LEMMA_API_KEY`    | Your Lemma API key    |
| `LEMMA_PROJECT_ID` | Your Lemma project ID |
| `LEMMA_API_URL`    | Optional. Override API base URL (e.g. `http://localhost:8000` for local dev) |

## License

MIT
