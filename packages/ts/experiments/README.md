# @uselemma/experiments

Run experiments against Lemma test cases — fetch cases, run your agent, record results and traces.

## Installation

```bash
npm install @uselemma/experiments
```

## Quick Start

```typescript
import { LemmaExperimentRunner } from "@uselemma/experiments";
import { callAgent } from "./call-agent";

const runner = new LemmaExperimentRunner();

await runner.runExperiment({
  experimentId: "exp_abc123",
  strategyName: "baseline",
  agent: async (input) => {
    const query = input.query ?? JSON.stringify(input);
    const { result, runId } = await callAgent([{ role: "user", content: query }]);
    await result.text;
    return { runId };
  },
});
```

## Environment Variables

| Variable           | Description           |
| ------------------ | --------------------- |
| `LEMMA_API_KEY`    | Your Lemma API key    |
| `LEMMA_PROJECT_ID` | Your Lemma project ID |
| `LEMMA_API_URL`    | Optional. Override API base URL (e.g. `http://localhost:8000` for local dev) |

## License

MIT
