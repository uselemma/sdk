from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider

from .register import register_otel


def instrument_anthropic(
    *,
    api_key: str | None = None,
    project_id: str | None = None,
    base_url: str = "https://api.uselemma.ai",
) -> TracerProvider:
    """Set up the Lemma tracer provider and auto-instrument the Anthropic SDK.

    Convenience wrapper that calls :func:`register_otel` and then patches
    the Anthropic client so every message call emits OTel spans to Lemma.

    Requires the ``anthropic`` extra::

        pip install "uselemma-tracing[anthropic]"

    Args:
        api_key: Lemma API key. Defaults to the ``LEMMA_API_KEY`` env var.
        project_id: Lemma project ID. Defaults to the ``LEMMA_PROJECT_ID`` env var.
        base_url: Base URL for the Lemma API.

    Returns:
        The configured :class:`TracerProvider`.
    """
    provider = register_otel(api_key=api_key, project_id=project_id, base_url=base_url)

    try:
        from openinference.instrumentation.anthropic import AnthropicInstrumentor
    except ImportError:
        raise ImportError(
            "Missing Anthropic instrumentation. "
            'Install with: pip install "uselemma-tracing[anthropic]"'
        )

    AnthropicInstrumentor().instrument()
    return provider
