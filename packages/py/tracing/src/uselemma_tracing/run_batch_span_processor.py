from __future__ import annotations

import threading
import uuid
from collections.abc import Mapping
from typing import Any

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span
from opentelemetry.sdk.trace.export import SpanExporter, SpanProcessor


class RunBatchSpanProcessor(SpanProcessor):
    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter
        self._lock = threading.Lock()
        self._shutdown = False
        self._span_id_to_run_id: dict[int, str] = {}
        self._batches: dict[str, list[ReadableSpan]] = {}
        self._ended_runs: set[str] = set()

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        span_id = span.context.span_id

        if self._is_top_level_run(span):
            run_id = self._get_attr(span, "lemma.run_id") or str(uuid.uuid4())
            span.set_attribute("lemma.run_id", run_id)
            with self._lock:
                self._span_id_to_run_id[span_id] = run_id
            return

        parent = getattr(span, "parent", None)
        if parent is None:
            return

        with self._lock:
            run_id = self._span_id_to_run_id.get(parent.span_id)
            if run_id is None:
                return

            self._span_id_to_run_id[span_id] = run_id

        span.set_attribute("lemma.run_id", run_id)

    def on_end(self, span: ReadableSpan) -> None:
        span_id = span.context.span_id
        parent = getattr(span, "parent", None)

        with self._lock:
            run_id = self._span_id_to_run_id.get(span_id)
            if run_id is None and parent is not None:
                run_id = self._span_id_to_run_id.get(parent.span_id)

            if run_id is None:
                return

            is_top_level_run = self._is_top_level_run(span)
            should_skip_export = self._should_skip_export(span)

            if not should_skip_export:
                self._batches.setdefault(run_id, []).append(span)

            if is_top_level_run:
                self._ended_runs.add(run_id)

        if is_top_level_run:
            self._export_run_batch(run_id, force=False)

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown:
                return

            self._shutdown = True

        self.force_flush()
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        with self._lock:
            run_ids = list(self._batches.keys())

        for run_id in run_ids:
            self._export_run_batch(run_id, force=True)

        flush_result = self._exporter.force_flush(timeout_millis=timeout_millis)
        return True if flush_result is None else bool(flush_result)

    def _export_run_batch(self, run_id: str, force: bool) -> None:
        with self._lock:
            if not force and run_id not in self._ended_runs:
                return

            batch = self._batches.pop(run_id, [])
            self._ended_runs.discard(run_id)
            self._clear_run_mapping_locked(run_id)

        if not batch:
            return

        self._exporter.export(batch)

    def _clear_run_mapping_locked(self, run_id: str) -> None:
        stale_span_ids = [
            span_id
            for span_id, mapped_run_id in self._span_id_to_run_id.items()
            if mapped_run_id == run_id
        ]
        for span_id in stale_span_ids:
            del self._span_id_to_run_id[span_id]

    @staticmethod
    def _is_top_level_run(span: Span | ReadableSpan) -> bool:
        return span.name == "ai.agent.run" and getattr(span, "parent", None) is None

    @staticmethod
    def _scope_name(span: Span | ReadableSpan) -> str | None:
        scope = getattr(span, "instrumentation_scope", None)
        return getattr(scope, "name", None)

    @classmethod
    def _should_skip_export(cls, span: Span | ReadableSpan) -> bool:
        return cls._scope_name(span) == "next.js"

    @staticmethod
    def _get_attr(span: Span, key: str) -> str | None:
        attributes = getattr(span, "attributes", None)
        if not isinstance(attributes, Mapping):
            return None
        value: Any = attributes.get(key)
        return value if isinstance(value, str) and value else None
