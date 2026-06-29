from __future__ import annotations

import json

import pytest

from uselemma_tracing.client import Lemma, active
from uselemma_tracing.debug_mode import disable_debug_mode, enable_debug_mode

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


def test_debug_mode_logs_sanitized_span_summaries(capsys):
    def transport(_url, _headers, _body):
        return 201, "{}"

    lemma = Lemma(api_key="key", project_id=PROJECT_ID, transport=transport)

    def run(trace):
        trace.record_tool(
            name="search_docs",
            input={"query": "secret query"},
            output={"status": "secret status"},
            duration_ms=25,
        )
        trace.record_generation(
            name="draft-reply",
            input="secret prompt",
            output="secret answer",
            model="gpt-test",
            usage={"input_tokens": 12, "output_tokens": 8},
            duration_ms=40,
        )
        live_output = capsys.readouterr().out
        assert live_output.count("[LEMMA:client] span recorded") == 2
        assert "[LEMMA:client] sending trace" not in live_output
        assert "'name': 'search_docs'" in live_output
        assert "'type': 'tool'" in live_output
        assert "'duration_ms': 25" in live_output
        assert "'name': 'draft-reply'" in live_output
        assert "'type': 'generation'" in live_output
        assert "'model': 'gpt-test'" in live_output
        assert "'input_tokens': 12" in live_output
        assert "'output_tokens': 8" in live_output
        assert "secret query" not in live_output
        assert "secret prompt" not in live_output
        assert "secret answer" not in live_output
        return "secret result"

    enable_debug_mode()
    try:
        lemma.trace("support-agent", run, input="secret trace input")
    finally:
        disable_debug_mode()

    output = capsys.readouterr().out
    assert "[LEMMA:client] sending trace" in output
    assert "'span_count': 2" in output
    assert "secret result" not in output


def test_debug_mode_logs_live_span_handles(capsys):
    def transport(_url, _headers, _body):
        return 201, "{}"

    lemma = Lemma(api_key="key", project_id=PROJECT_ID, transport=transport)

    def run(trace):
        span = trace.start_tool(name="search_docs", input={"query": "secret query"})
        started_output = capsys.readouterr().out
        assert "[LEMMA:client] span started" in started_output
        assert "'id':" in started_output
        assert "'name': 'search_docs'" in started_output
        assert "'type': 'tool'" in started_output
        assert "'has_input': True" in started_output
        assert "'has_output': False" in started_output
        assert "secret query" not in started_output

        span.end(output={"status": "secret status"}, duration_ms=25)
        ended_output = capsys.readouterr().out
        assert "[LEMMA:client] span ended" in ended_output
        assert "'name': 'search_docs'" in ended_output
        assert "'type': 'tool'" in ended_output
        assert "'duration_ms': 25" in ended_output
        assert "'has_input': True" in ended_output
        assert "'has_output': True" in ended_output
        assert "secret status" not in ended_output
        return "ok"

    enable_debug_mode()
    try:
        lemma.trace("support-agent", run)
    finally:
        disable_debug_mode()


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
