from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider

from .register import register_otel


def instrument_openai_agents(
    *,
    api_key: str | None = None,
    project_id: str | None = None,
    base_url: str = "https://api.uselemma.ai",
) -> TracerProvider:
    """Set up the Lemma tracer provider and auto-instrument the OpenAI Agents SDK.

    Convenience wrapper that calls :func:`register_otel` and then patches
    the OpenAI Agents SDK so every agent run, tool call, and handoff emits
    OTel spans to Lemma.

    Requires the ``openai-agents`` extra::

        pip install "uselemma-tracing[openai-agents]"

    Args:
        api_key: Lemma API key. Defaults to the ``LEMMA_API_KEY`` env var.
        project_id: Lemma project ID. Defaults to the ``LEMMA_PROJECT_ID`` env var.
        base_url: Base URL for the Lemma API.

    Returns:
        The configured :class:`TracerProvider`.
    """
    provider = register_otel(api_key=api_key, project_id=project_id, base_url=base_url)

    try:
        from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
    except ImportError:
        raise ImportError(
            "Missing OpenAI Agents instrumentation. "
            'Install with: pip install "uselemma-tracing[openai-agents]"'
        )

    OpenAIAgentsInstrumentor().instrument()
    return provider
