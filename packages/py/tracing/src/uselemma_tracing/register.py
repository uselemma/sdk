from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanProcessor
from .run_batch_span_processor import RunBatchSpanProcessor


def create_lemma_span_processor(
    *,
    api_key: str | None = None,
    project_id: str | None = None,
    base_url: str = "https://api.uselemma.ai",
) -> SpanProcessor:
    """Create a :class:`BatchSpanProcessor` pre-configured to export traces to Lemma.

    Use this when you need to add Lemma as one of several span processors on an
    existing :class:`TracerProvider` (e.g. for dual-export to Lemma and another
    backend simultaneously).

    Args:
        api_key: Lemma API key. Defaults to the ``LEMMA_API_KEY`` env var.
        project_id: Lemma project ID. Defaults to the ``LEMMA_PROJECT_ID`` env var.
        base_url: Base URL for the Lemma API.

    Returns:
        A :class:`BatchSpanProcessor` configured to send spans to Lemma.

    Raises:
        ValueError: If *api_key* or *project_id* cannot be resolved.

    Example::

        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry import trace
        from uselemma_tracing import create_lemma_span_processor

        provider = TracerProvider()
        provider.add_span_processor(create_lemma_span_processor())
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
        )
        trace.set_tracer_provider(provider)
    """
    api_key = api_key or os.environ.get("LEMMA_API_KEY")
    project_id = project_id or os.environ.get("LEMMA_PROJECT_ID")

    if not api_key or not project_id:
        raise ValueError(
            "uselemma-tracing: Missing API key and/or project ID. "
            "Set the LEMMA_API_KEY and LEMMA_PROJECT_ID environment variables "
            "or pass them to create_lemma_span_processor()."
        )

    exporter = OTLPSpanExporter(
        endpoint=f"{base_url}/otel/v1/traces",
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Lemma-Project-ID": project_id,
        },
    )

    return RunBatchSpanProcessor(exporter)


def register_otel(
    *,
    api_key: str | None = None,
    project_id: str | None = None,
    base_url: str = "https://api.uselemma.ai",
) -> TracerProvider:
    """Register an OpenTelemetry tracer provider configured to send traces to Lemma.

    Sets up a :class:`TracerProvider` with a :class:`BatchSpanProcessor` and
    :class:`OTLPSpanExporter` pointing at the Lemma ingest endpoint.

    Args:
        api_key: Lemma API key. Defaults to the ``LEMMA_API_KEY`` env var.
        project_id: Lemma project ID. Defaults to the ``LEMMA_PROJECT_ID`` env var.
        base_url: Base URL for the Lemma API.

    Returns:
        The configured :class:`TracerProvider`.

    Raises:
        ValueError: If *api_key* or *project_id* cannot be resolved.
    """
    provider = TracerProvider()
    provider.add_span_processor(create_lemma_span_processor(api_key=api_key, project_id=project_id, base_url=base_url))
    trace.set_tracer_provider(provider)

    return provider
