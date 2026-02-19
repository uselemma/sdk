# Lemma Tracing

OpenTelemetry-based tracing for AI agents. Capture inputs, outputs, timing, token usage, and errors — then view everything in [Lemma](https://uselemma.ai).

## Packages

| Package | Language | Path | Description |
| --- | --- | --- | --- |
| [`@uselemma/tracing`](packages/ts/tracing) | TypeScript | `packages/ts/tracing` | Node.js tracing SDK |
| [`uselemma-tracing`](packages/py/tracing) | Python | `packages/py/tracing` | Python tracing SDK |

## Getting Started

### TypeScript

```bash
npm install @uselemma/tracing
```

See the [TypeScript package README](packages/ts/tracing/README.md) for usage.

### Python

```bash
pip install uselemma-tracing
```

See the [Python package README](packages/py/tracing/README.md) for usage.

## Development

This is a polyglot monorepo managed with:

- **[pnpm](https://pnpm.io/)** workspaces for TypeScript packages
- **[Turborepo](https://turbo.build/)** for build orchestration and caching
- **[uv](https://docs.astral.sh/uv/)** for Python packages

### Prerequisites

- Node.js >= 18
- pnpm >= 9
- Python >= 3.11
- uv

### Build all TypeScript packages

```bash
pnpm install
pnpm build
```

### Install Python dependencies

```bash
uv sync
```

## Documentation

- [Tracing Overview](https://docs.uselemma.ai/tracing/overview)
- [Vercel AI SDK Integration](https://docs.uselemma.ai/tracing/integrations/vercel-ai-sdk)
- [OpenAI Agents Integration](https://docs.uselemma.ai/tracing/integrations/openai-agents)

## License

MIT
