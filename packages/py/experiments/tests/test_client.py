"""Tests for LemmaExperimentsClient."""

from __future__ import annotations

import json

import httpx
import pytest

from uselemma_experiments.client import LemmaExperimentsClient


def test_constructor_raises_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEMMA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Missing API key"):
        LemmaExperimentsClient()


@pytest.mark.asyncio
async def test_get_test_cases_returns_parsed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    mock_cases = [
        {"id": "tc-1", "inputData": {"query": "hello"}},
        {"id": "tc-2", "inputData": {"query": "world"}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if "test-cases" in str(request.url):
            return httpx.Response(200, json=mock_cases)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler=handler)
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)

    client = LemmaExperimentsClient(api_key="key")
    result = await client.get_test_cases("exp-123")

    assert result == mock_cases


@pytest.mark.asyncio
async def test_get_test_cases_raises_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handler=handler)
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)

    client = LemmaExperimentsClient(api_key="key")

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_test_cases("exp-123")


@pytest.mark.asyncio
async def test_record_results_posts_correct_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200)

    transport = httpx.MockTransport(handler=handler)
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)

    client = LemmaExperimentsClient(api_key="key")
    results = [
        {"runId": "run-1", "testCaseId": "tc-1"},
        {"runId": "run-2", "testCaseId": "tc-2"},
    ]

    await client.record_results("exp-123", "baseline", results)

    assert captured_request is not None
    assert captured_request.method == "POST"
    assert "results" in str(captured_request.url)
    assert captured_request.headers["content-type"] == "application/json"
    body = json.loads(captured_request.content)
    assert body["strategyName"] == "baseline"
    assert body["results"] == results


@pytest.mark.asyncio
async def test_record_results_raises_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Server Error")

    transport = httpx.MockTransport(handler=handler)
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)

    client = LemmaExperimentsClient(api_key="key")

    with pytest.raises(httpx.HTTPStatusError):
        await client.record_results(
            "exp-123",
            "baseline",
            [{"runId": "run-1", "testCaseId": "tc-1"}],
        )
