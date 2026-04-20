from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider

from .register import register_otel


def instrument_langchain(
    *,
    api_key: str | None = None,
    project_id: str | None = None,
    base_url: str = "https://api.uselemma.ai",
) -> TracerProvider:
    """Set up the Lemma tracer provider and auto-instrument LangChain + LangGraph.

    Convenience wrapper that calls :func:`register_otel` and then installs a
    global LangChain callback handler via
    ``langchain_core.tracers.context.register_configure_hook``. Every
    ``Runnable`` — including compiled LangGraph ``StateGraph`` instances —
    emits OTel spans to Lemma. LangGraph node names are surfaced via the
    ``metadata["langgraph_node"]`` field; internal Pregel steps tagged
    ``langsmith:hidden`` are filtered out by the instrumentor.

    Requires the ``langchain`` extra::

        pip install "uselemma-tracing[langchain]"

    Args:
        api_key: Lemma API key. Defaults to the ``LEMMA_API_KEY`` env var.
        project_id: Lemma project ID. Defaults to the ``LEMMA_PROJECT_ID`` env var.
        base_url: Base URL for the Lemma API.

    Returns:
        The configured :class:`TracerProvider`.
    """
    provider = register_otel(api_key=api_key, project_id=project_id, base_url=base_url)

    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
    except ImportError:
        raise ImportError(
            "Missing LangChain instrumentation. "
            'Install with: pip install "uselemma-tracing[langchain]"'
        )

    LangChainInstrumentor().instrument()
    return provider
