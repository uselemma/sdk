"""Minimal LangGraph + Lemma tracing example.

Prerequisites:
    pip install "uselemma-tracing[langchain]" langchain-openai langgraph python-dotenv

Environment variables:
    LEMMA_API_KEY    - Your Lemma API key
    LEMMA_PROJECT_ID - Your Lemma project ID
    OPENAI_API_KEY   - Your OpenAI API key

What this demonstrates:
    - A compiled LangGraph ``StateGraph`` with three nodes (classify -> respond -> log).
    - One call to :func:`instrument_langchain` wires LangChain's global callback
      handler, which LangGraph inherits automatically because compiled graphs
      are ``Runnable`` objects.
    - Each node becomes a child span whose name is taken from
      ``metadata["langgraph_node"]``.
    - The ``llm`` node's ``ChatOpenAI`` call nests under its node span.
    - Lemma's :func:`agent` wraps the whole invocation into a single
      ``ai.agent.run`` root span so the graph run is exported as one batch.
"""

from __future__ import annotations

import asyncio
from typing import TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from uselemma_tracing import TraceContext, agent, instrument_langchain

load_dotenv()

instrument_langchain(base_url="http://localhost:8000")


class SupportState(TypedDict):
    user_message: str
    category: str
    response: str


model = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def classify(state: SupportState) -> SupportState:
    """Classify the request into a coarse category with a cheap heuristic."""
    msg = state["user_message"].lower()
    if any(word in msg for word in ("invoice", "refund", "charge", "plan")):
        category = "billing"
    elif any(word in msg for word in ("401", "403", "error", "bug", "api")):
        category = "technical"
    else:
        category = "product"
    return {**state, "category": category}


def respond(state: SupportState) -> SupportState:
    """Generate a reply with an LLM — this produces a nested ChatOpenAI span."""
    system = {
        "billing": "You are a concise billing support specialist.",
        "technical": "You are a concise technical support specialist.",
        "product": "You are a concise product specialist.",
    }[state["category"]]
    result = model.invoke(
        [SystemMessage(content=system), HumanMessage(content=state["user_message"])]
    )
    return {**state, "response": result.content}


def log(state: SupportState) -> SupportState:
    """Terminal node — prints the final response for the demo."""
    print(f"[{state['category']}] {state['response']}")
    return state


workflow = (
    StateGraph(state_schema=SupportState)
    .add_node("classify", classify)
    .add_node("respond", respond)
    .add_node("log", log)
    .add_edge(START, "classify")
    .add_edge("classify", "respond")
    .add_edge("respond", "log")
    .add_edge("log", END)
)

graph = workflow.compile()


async def run_agent(user_message: str, ctx: TraceContext) -> str:
    state = await graph.ainvoke({"user_message": user_message})
    ctx.on_complete(state["response"])
    return state["response"]


async def main() -> None:
    wrapped = agent("langgraph-support-agent", run_agent)

    test_requests = [
        "My monthly invoice looks too high. How can I review charges?",
        "Our Python script gets HTTP 401 from your API after rotating keys.",
        "What is the fastest way to onboard a new teammate?",
    ]

    for i, user_message in enumerate(test_requests, start=1):
        result, run_id, _span = await wrapped(user_message)
        print(f"--- Run {i} (run_id={run_id}) ---")


asyncio.run(main())
