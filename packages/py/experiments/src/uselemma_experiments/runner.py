"""LemmaExperimentRunner - orchestrate experiment runs."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from uselemma_tracing import enable_experiment_mode, register_otel

from .client import LemmaExperimentsClient
from .types import ExperimentResult, ExperimentSummary, TestCase


class LemmaExperimentRunner:
    """Run experiments: fetch test cases, run agent, flush traces, record results."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        project_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        api_key = api_key or os.environ.get("LEMMA_API_KEY")
        project_id = project_id or os.environ.get("LEMMA_PROJECT_ID")
        base_url = base_url or os.environ.get("LEMMA_API_URL") or "https://api.uselemma.ai"

        self._tracer_provider = register_otel(
            api_key=api_key,
            project_id=project_id,
            base_url=base_url,
        )
        enable_experiment_mode()

        self._client = LemmaExperimentsClient(
            api_key=api_key,
            base_url=base_url,
        )

    async def run_experiment(
        self,
        experiment_id: str,
        strategy_name: str,
        agent: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        *,
        concurrency: int | None = None,
        progress: bool = True,
    ) -> ExperimentSummary:
        """Run the agent on all test cases, flush traces, and record results."""
        test_cases = await self._client.get_test_cases(experiment_id)
        total = len(test_cases)
        results: list[ExperimentResult] = []

        async def run_one(test_case: TestCase) -> ExperimentResult | None:
            try:
                out = await agent(test_case["inputData"])
                run_id = out.get("runId") or out.get("run_id")
                if not run_id:
                    return None
                return {"runId": run_id, "testCaseId": test_case["id"]}
            except Exception:
                return None

        if concurrency is not None and concurrency > 0:
            sem = asyncio.Semaphore(concurrency)

            async def bounded_run(test_case: TestCase) -> ExperimentResult | None:
                async with sem:
                    return await run_one(test_case)

            tasks = [bounded_run(tc) for tc in test_cases]
            if progress and total > 0:
                from tqdm.asyncio import tqdm_asyncio

                completed = await tqdm_asyncio.gather(*tasks, desc="Experiment")
            else:
                completed = await asyncio.gather(*tasks)
        else:
            if progress and total > 0:
                from tqdm.asyncio import tqdm_asyncio

                completed = await tqdm_asyncio.gather(
                    *[run_one(tc) for tc in test_cases],
                    desc="Experiment",
                )
            else:
                completed = await asyncio.gather(*[run_one(tc) for tc in test_cases])

        for r in completed:
            if r is not None:
                results.append(r)

        await self._tracer_provider.force_flush()
        await self._client.record_results(experiment_id, strategy_name, results)

        return {"successful": len(results), "total": total}
