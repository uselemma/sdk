# Lemma SDK

Official SDKs for sending AI agent traces to Lemma.

This repository contains the TypeScript and Python tracing SDKs. The SDKs send
trace payloads directly to Lemma over HTTP and provide helpers for recording
agent runs, spans, generations, tools, timing, errors, and common
OpenInference-compatible attributes.

For instrumentation guides and the full trace contract, use the product docs:

- [Tracing overview](https://docs.uselemma.ai/tracing/overview)
- [Quickstart](https://docs.uselemma.ai/getting-started/quickstart)
- [Trace contract](https://docs.uselemma.ai/reference/trace-contract)
- [Debug mode](https://docs.uselemma.ai/tracing/troubleshooting/debug-mode)

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

You can also pass credentials directly to the client constructor. The default
API base URL is `https://api.uselemma.ai`; override it with `baseUrl` /
`base_url` when developing locally or targeting a self-hosted API router.

## Integrations

The SDKs include helpers for:

- Manual tracing with callback traces, trace handles, span handles, and
  record-by-ID helpers.
- Vercel AI SDK v7 and v6 in TypeScript.
- OpenAI Agents SDK in TypeScript and Python.
- LangChain and LangGraph in TypeScript and Python.
- Langfuse compatibility for sending Lemma traces alongside an existing
  Langfuse setup.

See the package READMEs for SDK-specific API notes:

- [TypeScript tracing package](packages/ts/tracing/README.md)
- [Python tracing package](packages/py/tracing/README.md)

## Development

Install dependencies:

```bash
pnpm install
uv sync
```

Run TypeScript checks:

```bash
pnpm --filter @uselemma/tracing test
pnpm --filter @uselemma/tracing type-check
pnpm --filter @uselemma/tracing build
```

Run Python checks:

```bash
uv run --project packages/py/tracing pytest packages/py/tracing/tests
uv build --package uselemma-tracing
```

## Releases

Publishing is driven by versioned Git tags:

- `ts/vX.Y.Z` publishes `@uselemma/tracing` to npm.
- `py/vX.Y.Z` publishes `uselemma-tracing` to PyPI.

Update the package version first, commit the change, push it to `main`, then
push the matching release tag.

## License

MIT
