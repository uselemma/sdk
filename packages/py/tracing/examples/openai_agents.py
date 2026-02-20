"""Minimal OpenAI Agents SDK + Lemma tracing example.

Prerequisites:
    pip install "uselemma-tracing[openai-agents]" openai-agents

Environment variables:
    LEMMA_API_KEY    - Your Lemma API key
    LEMMA_PROJECT_ID - Your Lemma project ID
    OPENAI_API_KEY   - Your OpenAI API key
"""

import asyncio
import random

from agents import Agent, Runner, function_tool
from dotenv import load_dotenv
from uselemma_tracing import TraceContext, instrument_openai_agents, wrap_agent

load_dotenv()

instrument_openai_agents(base_url="http://localhost:8000")


async def _maybe_fail_tool_call(tool_name: str) -> None:
    """Randomly inject failures into tool calls for resilience testing."""
    rate = 0.3
    tool_names = {"*"}

    tool_selected = "*" in tool_names or tool_name in tool_names
    if not tool_selected or random.random() >= rate:
        return

    raise RuntimeError(f"Simulated tool failure in tool: {tool_name}")


@function_tool
async def fetch_invoice_summary(account_id: str) -> str:
    """Fake billing backend lookup for testing tool-call tracing."""
    await _maybe_fail_tool_call("fetch_invoice_summary")
    await asyncio.sleep(0.1)
    return (
        f"Invoice summary for {account_id}: "
        "Plan=Pro Monthly ($49), Seats=3, Overage=$12, "
        "Last payment=successful, Refund eligibility=partial within 14 days."
    )


@function_tool
async def diagnose_auth_error(service_name: str, http_status: int) -> str:
    """Fake technical diagnosis helper for auth/API troubleshooting."""
    await _maybe_fail_tool_call("diagnose_auth_error")
    await asyncio.sleep(0.1)
    if http_status == 401:
        return (
            f"{service_name}: likely invalid or expired API key. "
            "Verify key rotation order, environment propagation, and token audience."
        )
    if http_status == 403:
        return f"{service_name}: likely permission scope issue. Check role and project bindings."
    return f"{service_name}: inspect server logs and request signatures for auth mismatches."


@function_tool
async def get_onboarding_checklist(team_size: int) -> str:
    """Fake product playbook lookup for onboarding guidance."""
    await _maybe_fail_tool_call("get_onboarding_checklist")
    await asyncio.sleep(0.1)
    return (
        f"Suggested onboarding for team size {team_size}: "
        "create workspace template, assign starter tutorial, "
        "set weekly check-ins, and enable baseline alerts."
    )


billing_agent = Agent(
    name="Billing specialist",
    instructions=(
        "You are a billing support specialist. "
        "Handle invoices, subscription plans, and refund policies. "
        "Use fetch_invoice_summary when account details are relevant. "
        "Be concise and include next steps."
    ),
    tools=[fetch_invoice_summary],
)


technical_agent = Agent(
    name="Technical specialist",
    instructions=(
        "You are a technical support specialist for a SaaS product. "
        "Handle debugging, API errors, and troubleshooting workflows. "
        "Use diagnose_auth_error for auth/API issues before final guidance. "
        "When helpful, provide numbered steps."
    ),
    tools=[diagnose_auth_error],
)


product_agent = Agent(
    name="Product specialist",
    instructions=(
        "You are a product specialist. "
        "Handle feature education, onboarding, and best-practice usage guidance. "
        "Use get_onboarding_checklist for onboarding/setup requests. "
        "Offer practical examples."
    ),
    tools=[get_onboarding_checklist],
)


triage_agent = Agent(
    name="Triage router",
    instructions=(
        "Route each user request to the most appropriate specialist:\n"
        "- Billing specialist for pricing, invoices, refunds, or subscriptions.\n"
        "- Technical specialist for code, API, bugs, or errors.\n"
        "- Product specialist for how-to questions and workflow setup."
    ),
    handoffs=[billing_agent, technical_agent, product_agent],
)


async def run_agent(ctx: TraceContext, user_message: str) -> str:
    result = await Runner.run(triage_agent, user_message)
    ctx.on_complete(result.final_output)
    return result.final_output


async def main():
    wrapped = wrap_agent("triage-support-agent", run_agent)

    test_requests = [
        "My monthly invoice looks too high. How can I review charges and request a refund?",
        "Our Python script gets HTTP 401 from your API after rotating keys. How do we fix this?",
        "What is the fastest way to onboard a new teammate and set up project templates?",
    ]

    for i, user_message in enumerate(test_requests, start=1):
        result, run_id, span = await wrapped(user_message)
        print(f"\n--- Run {i} ---")


asyncio.run(main())
