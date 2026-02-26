"""Type definitions for uselemma_experiments."""

from __future__ import annotations

from typing import Any, TypedDict


class TestCase(TypedDict):
    """A single test case from an experiment."""

    id: str
    inputData: dict[str, Any]


class ExperimentResult(TypedDict):
    """Result of running an agent on a test case."""

    runId: str
    testCaseId: str


class LemmaExperimentRunnerOptions(TypedDict, total=False):
    """Options passed to LemmaExperimentRunner constructor."""

    api_key: str
    project_id: str
    base_url: str


class ExperimentSummary(TypedDict):
    """Summary of an experiment run."""

    successful: int
    total: int
