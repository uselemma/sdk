"""HTTP client for Lemma experiments API."""

from __future__ import annotations

import os

import httpx

from .types import ExperimentResult, TestCase

DEFAULT_BASE_URL = "https://api.uselemma.ai"


class LemmaExperimentsClient:
    """Client for fetching test cases and recording results."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("LEMMA_API_KEY") or ""
        self._base_url = (
            base_url
            or os.environ.get("LEMMA_API_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")

        if not self._api_key:
            raise ValueError(
                "LemmaExperimentsClient: Missing API key. "
                "Set LEMMA_API_KEY environment variable or pass api_key to the constructor."
            )

    async def get_test_cases(self, experiment_id: str) -> list[TestCase]:
        """Fetch test cases for an experiment."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/experiments/{experiment_id}/test-cases",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            return response.json()

    async def record_results(
        self,
        experiment_id: str,
        strategy_name: str,
        results: list[ExperimentResult],
    ) -> None:
        """Record experiment results."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/experiments/{experiment_id}/results",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                json={"strategyName": strategy_name, "results": results},
            )
            response.raise_for_status()
