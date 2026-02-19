"""Minimal OpenAI Agents SDK + Lemma tracing example.

Prerequisites:
    pip install "uselemma-tracing[openai-agents]" openai-agents

Environment variables:
    LEMMA_API_KEY    - Your Lemma API key
    LEMMA_PROJECT_ID - Your Lemma project ID
    OPENAI_API_KEY   - Your OpenAI API key
"""

import asyncio

from dotenv import load_dotenv

load_dotenv()

from uselemma_tracing import TraceContext, instrument_openai_agents, wrap_agent

instrument_openai_agents()

from agents import Agent, Runner

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant. Keep responses concise.",
)


async def run_agent(ctx: TraceContext, user_message: str):
    result = await Runner.run(agent, user_message)
    ctx.on_complete(result.final_output)
    return result.final_output


async def main():
    user_message = "What is 2 + 2?"

    wrapped = wrap_agent(
        "assistant",
        run_agent,
        initial_state={"user_message": user_message},
    )

    result, run_id, span = await wrapped(user_message)
    print(f"run_id: {run_id}")
    print(f"result: {result}")


asyncio.run(main())
