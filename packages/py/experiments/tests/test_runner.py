"""Tests for LemmaExperimentRunner."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from uselemma_experiments.runner import LemmaExperimentRunner


@pytest.fixture
def fake_client() -> MagicMock:
    client = MagicMock()
    client.get_test_cases = AsyncMock()
    client.record_results = AsyncMock()
    return client


@pytest.fixture
def fake_tracer_provider() -> MagicMock:
    provider = MagicMock()
    provider.force_flush = AsyncMock()
    return provider


@pytest.mark.asyncio
async def test_constructor_calls_enable_experiment_mode(
    monkeypatch: pytest.MonkeyPatch,
    fake_tracer_provider: MagicMock,
    fake_client: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    mock_enable = MagicMock()
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        mock_enable,
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    LemmaExperimentRunner()

    mock_enable.assert_called_once()


@pytest.mark.asyncio
async def test_run_experiment_calls_agent_with_input_data(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: MagicMock,
    fake_tracer_provider: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        MagicMock(),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    test_cases = [
        {"id": "tc-1", "inputData": {"query": "hello"}},
        {"id": "tc-2", "inputData": {"query": "world"}},
    ]
    fake_client.get_test_cases.return_value = test_cases

    agent = AsyncMock(side_effect=lambda inp: {"runId": f"run-{inp['query']}"})

    runner = LemmaExperimentRunner()
    await runner.run_experiment(
        "exp-1",
        "baseline",
        agent,
        progress=False,
    )

    agent.assert_any_call({"query": "hello"})
    agent.assert_any_call({"query": "world"})
    assert not any(
        "id" in (call[0][0] if call[0] else {})
        for call in agent.call_args_list
    )


@pytest.mark.asyncio
async def test_run_experiment_excludes_failed_agents(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: MagicMock,
    fake_tracer_provider: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        MagicMock(),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    test_cases = [
        {"id": "tc-1", "inputData": {"q": 1}},
        {"id": "tc-2", "inputData": {"q": 2}},
        {"id": "tc-3", "inputData": {"q": 3}},
    ]
    fake_client.get_test_cases.return_value = test_cases

    async def agent(inp: dict[str, Any]) -> dict[str, Any]:
        if inp.get("q") == 2:
            raise ValueError("fail")
        return {"runId": f"run-{inp['q']}"}

    runner = LemmaExperimentRunner()
    summary = await runner.run_experiment(
        "exp-1",
        "baseline",
        agent,
        progress=False,
    )

    assert summary == {"successful": 2, "total": 3}
    fake_client.record_results.assert_called_once()
    call_args = fake_client.record_results.call_args[0]
    assert call_args[0] == "exp-1"
    assert call_args[1] == "baseline"
    results = call_args[2]
    assert len(results) == 2
    assert {r["testCaseId"] for r in results} == {"tc-1", "tc-3"}


@pytest.mark.asyncio
async def test_force_flush_called_before_record_results(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: MagicMock,
    fake_tracer_provider: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        MagicMock(),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    fake_client.get_test_cases.return_value = [{"id": "tc-1", "inputData": {}}]
    call_order: list[str] = []

    async def track_flush() -> None:
        call_order.append("flush")

    async def track_record(*args: object, **kwargs: object) -> None:
        call_order.append("record")

    fake_tracer_provider.force_flush.side_effect = track_flush
    fake_client.record_results.side_effect = track_record

    runner = LemmaExperimentRunner()
    await runner.run_experiment(
        "exp-1",
        "baseline",
        AsyncMock(return_value={"runId": "run-1"}),
        progress=False,
    )

    assert call_order == ["flush", "record"]


@pytest.mark.asyncio
async def test_record_results_receives_correct_args(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: MagicMock,
    fake_tracer_provider: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        MagicMock(),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    fake_client.get_test_cases.return_value = [
        {"id": "tc-a", "inputData": {"x": 1}},
    ]

    runner = LemmaExperimentRunner()
    await runner.run_experiment(
        "exp-99",
        "my-strategy",
        AsyncMock(return_value={"runId": "run-xyz"}),
        progress=False,
    )

    fake_client.record_results.assert_called_once_with(
        "exp-99",
        "my-strategy",
        [{"runId": "run-xyz", "testCaseId": "tc-a"}],
    )


@pytest.mark.asyncio
async def test_returns_correct_experiment_summary(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: MagicMock,
    fake_tracer_provider: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        MagicMock(),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    fake_client.get_test_cases.return_value = [
        {"id": "tc-1", "inputData": {}},
        {"id": "tc-2", "inputData": {}},
    ]

    runner = LemmaExperimentRunner()
    summary = await runner.run_experiment(
        "exp-1",
        "baseline",
        AsyncMock(return_value={"runId": "run-1"}),
        progress=False,
    )

    assert summary == {"successful": 2, "total": 2}


@pytest.mark.asyncio
async def test_progress_false_skips_tqdm(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: MagicMock,
    fake_tracer_provider: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        MagicMock(),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    fake_client.get_test_cases.return_value = [{"id": "tc-1", "inputData": {}}]

    runner = LemmaExperimentRunner()
    summary = await runner.run_experiment(
        "exp-1",
        "baseline",
        AsyncMock(return_value={"runId": "run-1"}),
        progress=False,
    )

    assert summary["successful"] == 1
    assert summary["total"] == 1


@pytest.mark.asyncio
async def test_concurrency_limits_parallel_execution(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: MagicMock,
    fake_tracer_provider: MagicMock,
) -> None:
    monkeypatch.setenv("LEMMA_API_KEY", "key")
    monkeypatch.setenv("LEMMA_PROJECT_ID", "proj")
    monkeypatch.setattr(
        "uselemma_experiments.runner.register_otel",
        MagicMock(return_value=fake_tracer_provider),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.enable_experiment_mode",
        MagicMock(),
    )
    monkeypatch.setattr(
        "uselemma_experiments.runner.LemmaExperimentsClient",
        lambda **kwargs: fake_client,
    )

    fake_client.get_test_cases.return_value = [
        {"id": "tc-1", "inputData": {}},
        {"id": "tc-2", "inputData": {}},
        {"id": "tc-3", "inputData": {}},
    ]

    concurrent = 0
    max_concurrent = 0

    async def agent(inp: dict[str, Any]) -> dict[str, Any]:
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        import asyncio
        await asyncio.sleep(0.01)
        concurrent -= 1
        return {"runId": "run-1"}

    runner = LemmaExperimentRunner()
    await runner.run_experiment(
        "exp-1",
        "baseline",
        agent,
        concurrency=2,
        progress=False,
    )

    assert max_concurrent <= 2
