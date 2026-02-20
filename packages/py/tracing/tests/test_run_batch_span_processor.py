from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from uselemma_tracing.run_batch_span_processor import RunBatchSpanProcessor


@dataclass
class _FakeSpanContext:
    span_id: int


@dataclass
class _FakeParent:
    span_id: int


@dataclass
class _FakeScope:
    name: str


@dataclass
class _FakeSpan:
    name: str
    span_id: int
    parent: _FakeParent | None = None
    scope_name: str = "lemma"
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def context(self) -> _FakeSpanContext:
        return _FakeSpanContext(span_id=self.span_id)

    @property
    def instrumentation_scope(self) -> _FakeScope:
        return _FakeScope(name=self.scope_name)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class _FakeExporter:
    def __init__(self) -> None:
        self.exports: list[list[_FakeSpan]] = []
        self.force_flush_calls = 0
        self.shutdown_calls = 0

    def export(self, spans):
        self.exports.append(list(spans))
        return None

    def force_flush(self, timeout_millis: int = 30000):
        self.force_flush_calls += 1
        return True

    def shutdown(self):
        self.shutdown_calls += 1
        return None


def test_run_batch_auto_ends_root_once_direct_children_are_done():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": "run-a"},
    )
    child = _FakeSpan(name="ai.step", span_id=2, parent=_FakeParent(span_id=1))

    processor.on_start(root)
    processor.on_start(child)
    processor.on_end(child)
    assert len(exporter.exports) == 1
    assert [span.span_id for span in exporter.exports[0]] == [2, 1]


def test_nextjs_scope_spans_are_skipped():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=10,
        parent=None,
        attributes={"lemma.run_id": "run-next"},
    )
    nextjs_span = _FakeSpan(
        name="middleware",
        span_id=11,
        parent=_FakeParent(span_id=10),
        scope_name="next.js",
    )

    processor.on_start(root)
    processor.on_start(nextjs_span)
    processor.on_end(nextjs_span)
    processor.on_end(root)

    assert len(exporter.exports) == 1
    assert [span.span_id for span in exporter.exports[0]] == [10]


def test_export_waits_for_direct_child_that_ends_after_root():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=100,
        parent=None,
        attributes={"lemma.run_id": "run-late-child"},
    )
    child = _FakeSpan(name="ai.step", span_id=101, parent=_FakeParent(span_id=100))

    processor.on_start(root)
    processor.on_start(child)

    processor.on_end(root)
    assert exporter.exports == []

    processor.on_end(child)
    assert len(exporter.exports) == 1
    assert [span.span_id for span in exporter.exports[0]] == [100, 101]


def test_force_flush_exports_each_run_in_separate_batch():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    run1 = _FakeSpan(
        name="ai.agent.run",
        span_id=20,
        parent=None,
        attributes={"lemma.run_id": "run-1"},
    )
    run2 = _FakeSpan(
        name="ai.agent.run",
        span_id=30,
        parent=None,
        attributes={"lemma.run_id": "run-2"},
    )
    child1 = _FakeSpan(name="child", span_id=21, parent=_FakeParent(span_id=20))
    child2 = _FakeSpan(name="child", span_id=31, parent=_FakeParent(span_id=30))

    for span in (run1, run2, child1, child2):
        processor.on_start(span)

    processor.on_end(child1)
    processor.on_end(child2)

    processor.force_flush()

    assert len(exporter.exports) == 2
    assert [batch[0].span_id for batch in exporter.exports] == [21, 31]
    assert exporter.force_flush_calls == 1
