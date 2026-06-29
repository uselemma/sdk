from __future__ import annotations

import json

import pytest

from uselemma_tracing.client import Lemma, active

PROJECT_ID = "10000000-0000-0000-0000-000000000001"


def test_lemma_trace_posts_completed_trace():
    calls = []

    def transport(url, headers, body):
        calls.append((url, headers, json.loads(body.decode())))
        return 201, "{}"

    lemma = Lemma(
        api_key="key",
        project_id=PROJECT_ID,
        base_url="https://api.example.test",
        transport=transport,
    )

    result = lemma.trace(
        "support-agent",
        lambda trace: (
            trace.record_tool(
                name="search_docs",
                input={"query": "order"},
                output={"status": "shipped"},
                duration_ms=25,
                tool_parameters={"query": "string"},
            ),
            active().generation(
                name="draft-reply",
                input="prompt",
                output="answer",
                model="gpt-4o",
                usage={"input_tokens": 12, "output_tokens": 8},
                duration_ms=40,
                llm_invocation_parameters={"temperature": 0.2},
                llm_input_messages=[{"role": "user", "content": "where is my order?"}],
            ),
            "it arrives Friday",
        )[-1],
        input="where is my order?",
        thread_id="thread-1",
        user_id="user-1",
        duration_ms=1234,
    )

    assert result == "it arrives Friday"
    assert len(calls) == 1
    url, headers, body = calls[0]
    assert url == "https://api.example.test/traces/ingest"
    assert headers["Authorization"] == "Bearer key"
    assert body["project_id"] == PROJECT_ID
    assert body["trace"]["name"] == "support-agent"
    assert body["trace"]["input"] == "where is my order?"
    assert body["trace"]["output"] == "it arrives Friday"
    assert body["trace"]["thread_id"] == "thread-1"
    assert body["trace"]["user_id"] == "user-1"
    assert body["trace"]["duration_ms"] == 1234
    assert body["trace"]["spans"][0]["type"] == "tool"
    assert body["trace"]["spans"][0]["duration_ms"] == 25
    assert body["trace"]["spans"][0]["attributes"] == {
        "tool.parameters": '{"query":"string"}',
    }
    assert body["trace"]["spans"][1]["type"] == "generation"
    assert body["trace"]["spans"][1]["duration_ms"] == 40
    assert body["trace"]["spans"][1]["attributes"] == {
        "llm.invocation_parameters": '{"temperature":0.2}',
        "llm.input_messages.0.message.role": "user",
        "llm.input_messages.0.message.content": "where is my order?",
        "llm.model_name": "gpt-4o",
        "llm.token_count.prompt": 12,
        "llm.token_count.completion": 8,
    }
    assert body["trace"]["spans"][1]["usage"] == {
        "input_tokens": 12,
        "output_tokens": 8,
    }


def test_lemma_trace_omits_unspecified_child_duration():
    calls = []

    def transport(_url, _headers, body):
        calls.append(json.loads(body.decode()))
        return 201, "{}"

    lemma = Lemma(api_key="key", project_id=PROJECT_ID, transport=transport)

    lemma.trace(
        "support-agent",
        lambda trace: trace.record_tool(name="lookup", input={"id": "order-1"}),
        duration_ms=1000,
    )

    body = calls[0]
    assert "duration_ms" not in body["trace"]["spans"][0]


def test_lemma_trace_supports_record_aliases_and_live_tool_generation_handles():
    calls = []

    def transport(_url, _headers, body):
        calls.append(json.loads(body.decode()))
        return 201, "{}"

    lemma = Lemma(api_key="key", project_id=PROJECT_ID, transport=transport)

    def run(trace):
        trace.record_tool(name="lookup", output={"ok": True}, duration_ms=10)
        trace.record_generation(name="draft", output="hello", duration_ms=20)

        tool = trace.start_tool(name="search_docs", input={"query": "order"})
        tool.end(output=[{"title": "Shipping"}], duration_ms=30)

        generation = trace.start_generation(name="answer", input="prompt")
        generation.end(output="It arrives Friday.", duration_ms=40)

        return "ok"

    lemma.trace("support-agent", run)

    spans = calls[0]["trace"]["spans"]
    assert spans[0]["type"] == "tool"
    assert spans[0]["duration_ms"] == 10
    assert spans[1]["type"] == "generation"
    assert spans[1]["duration_ms"] == 20
    assert spans[2]["type"] == "tool"
    assert spans[2]["duration_ms"] == 30
    assert spans[3]["type"] == "generation"
    assert spans[3]["duration_ms"] == 40


def test_lemma_trace_flushes_errors_and_reraises():
    calls = []

    def transport(url, headers, body):
        calls.append(json.loads(body.decode()))
        return 201, "{}"

    lemma = Lemma(api_key="key", project_id=PROJECT_ID, transport=transport)

    def run(trace):
        trace.record_tool(name="lookup", error=ValueError("missing"))
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        lemma.trace("support-agent", run)

    body = calls[0]
    assert body["trace"]["status"] == "ERROR"
    assert body["trace"]["error"] == "boom"
    assert body["trace"]["spans"][0]["status"] == "ERROR"
    assert body["trace"]["spans"][0]["error"] == "missing"


def test_lemma_trace_surfaces_ingest_failures():
    lemma = Lemma(
        api_key="key",
        project_id=PROJECT_ID,
        transport=lambda _url, _headers, _body: (503, "nope"),
    )

    with pytest.raises(RuntimeError, match="failed to ingest trace"):
        lemma.trace("support-agent", lambda _trace: "ok")


async def test_lemma_async_trace_posts_completed_trace():
    calls = []

    def transport(url, headers, body):
        calls.append(json.loads(body.decode()))
        return 201, "{}"

    lemma = Lemma(api_key="key", project_id=PROJECT_ID, transport=transport)

    async def run(trace):
        trace.record_generation(name="answer", output="hello")
        return "hello"

    result = await lemma.async_trace("async-agent", run, input="hi")

    assert result == "hello"
    assert calls[0]["trace"]["name"] == "async-agent"
    assert calls[0]["trace"]["output"] == "hello"
    assert calls[0]["trace"]["spans"][0]["type"] == "generation"
