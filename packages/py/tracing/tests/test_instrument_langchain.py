"""Verifies that ``instrument_langchain`` actually traces LangGraph runs.

Does not require a ``LEMMA_API_KEY`` or a real Lemma endpoint: we stub the env
vars, call ``instrument_langchain``, and then attach an in-memory exporter to
whichever tracer provider the LangChain instrumentor is writing into.
"""

from __future__ import annotations

import os
from typing import TypedDict

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class SupportState(TypedDict):
    user_message: str
    category: str


@pytest.fixture
def in_memory_exporter() -> InMemorySpanExporter:
    os.environ.setdefault("LEMMA_API_KEY", "test-key")
    os.environ.setdefault("LEMMA_PROJECT_ID", "test-project")

    from uselemma_tracing import instrument_langchain

    instrument_langchain(base_url="http://localhost:65535")

    active_provider = trace.get_tracer_provider()
    assert isinstance(active_provider, TracerProvider), (
        "expected an SDK TracerProvider after instrument_langchain(); "
        f"got {type(active_provider)!r}"
    )

    exporter = InMemorySpanExporter()
    active_provider.add_span_processor(SimpleSpanProcessor(exporter))

    try:
        yield exporter
    finally:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().uninstrument()


def test_langgraph_nodes_are_traced(in_memory_exporter: InMemorySpanExporter) -> None:
    from langgraph.graph import END, START, StateGraph

    def classify(state: SupportState) -> SupportState:
        msg = state["user_message"].lower()
        category = "billing" if "invoice" in msg else "product"
        return {**state, "category": category}

    def respond(state: SupportState) -> SupportState:
        return state

    graph = (
        StateGraph(state_schema=SupportState)
        .add_node("classify", classify)
        .add_node("respond", respond)
        .add_edge(START, "classify")
        .add_edge("classify", "respond")
        .add_edge("respond", END)
        .compile()
    )

    graph.invoke({"user_message": "My invoice looks wrong"})

    span_names = {span.name for span in in_memory_exporter.get_finished_spans()}

    assert "LangGraph" in span_names, (
        f"expected a LangGraph root span; got {sorted(span_names)!r}"
    )
    assert "classify" in span_names, (
        f"expected a classify node span; got {sorted(span_names)!r}"
    )
    assert "respond" in span_names, (
        f"expected a respond node span; got {sorted(span_names)!r}"
    )
