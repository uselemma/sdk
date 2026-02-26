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
    ended: bool = field(default=False, repr=False)
    instrumentation_scope_none: bool = field(default=False, repr=False)

    @property
    def context(self) -> _FakeSpanContext:
        return _FakeSpanContext(span_id=self.span_id)

    @property
    def instrumentation_scope(self) -> _FakeScope | None:
        if self.instrumentation_scope_none:
            return None
        return _FakeScope(name=self.scope_name)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.ended = True


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
        attributes={"lemma.run_id": "run-a", "lemma.auto_end_root": True},
    )
    child = _FakeSpan(name="ai.step", span_id=2, parent=_FakeParent(span_id=1))

    processor.on_start(root)
    processor.on_start(child)
    processor.on_end(child)
    processor.on_end(root)
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


def test_shutdown_calls_force_flush_and_exporter_shutdown():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    processor.shutdown()

    assert exporter.force_flush_calls == 1
    assert exporter.shutdown_calls == 1


def test_shutdown_idempotent():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    processor.shutdown()
    processor.shutdown()

    assert exporter.shutdown_calls == 1


def test_grandchild_span_attributed_to_run_not_counted_as_direct_child():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": "run-a"},
    )
    child = _FakeSpan(name="ai.step", span_id=2, parent=_FakeParent(span_id=1))
    grandchild = _FakeSpan(name="ai.substep", span_id=3, parent=_FakeParent(span_id=2))

    processor.on_start(root)
    processor.on_start(child)
    processor.on_start(grandchild)
    processor.on_end(grandchild)
    processor.on_end(child)
    processor.on_end(root)

    assert len(exporter.exports) == 1
    span_ids = [s.span_id for s in exporter.exports[0]]
    assert 1 in span_ids
    assert 2 in span_ids
    assert 3 in span_ids


def test_root_without_lemma_run_id_auto_generates():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={},
    )

    processor.on_start(root)
    assert "lemma.run_id" in root.attributes
    assert isinstance(root.attributes["lemma.run_id"], str)
    assert len(root.attributes["lemma.run_id"]) > 0

    processor.on_end(root)
    assert len(exporter.exports) == 1
    assert exporter.exports[0][0].span_id == 1


def test_force_flush_clears_direct_child_mapping():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": "run-flush"},
    )
    child = _FakeSpan(name="child", span_id=2, parent=_FakeParent(span_id=1))

    processor.on_start(root)
    processor.on_start(child)
    processor.on_end(root)
    processor.force_flush()

    assert len(exporter.exports) == 1
    assert processor._direct_child_span_id_to_run_id == {}


def test_force_flush_with_no_pending_batches():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    result = processor.force_flush()

    assert result is True
    assert exporter.exports == []
    assert exporter.force_flush_calls == 1


def test_export_run_batch_empty_batch_skips_export():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": "run-empty"},
    )
    nextjs_child = _FakeSpan(
        name="middleware",
        span_id=2,
        parent=_FakeParent(span_id=1),
        scope_name="next.js",
    )

    processor.on_start(root)
    processor.on_start(nextjs_child)
    processor.on_end(nextjs_child)
    processor.on_end(root)

    assert len(exporter.exports) == 1
    assert [s.span_id for s in exporter.exports[0]] == [1]

    processor._batches["run-empty"] = []
    processor._export_run_batch("run-empty", force=True)

    assert len(exporter.exports) == 1


def test_on_start_span_with_no_parent_and_not_top_level_returns_early():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    span = _FakeSpan(name="other.span", span_id=1, parent=None)
    processor.on_start(span)

    assert len(exporter.exports) == 0


def test_on_start_span_with_parent_not_in_map_returns_early():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    span = _FakeSpan(name="child", span_id=2, parent=_FakeParent(span_id=999))
    processor.on_start(span)

    assert len(exporter.exports) == 0


def test_on_end_span_with_no_run_id_returns_early():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    span = _FakeSpan(name="orphan", span_id=1, parent=None)
    processor.on_end(span)

    assert len(exporter.exports) == 0


def test_on_end_span_gets_run_id_from_parent_when_self_not_in_map():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": "run-x"},
    )
    child = _FakeSpan(name="child", span_id=2, parent=_FakeParent(span_id=1))

    processor.on_start(root)
    processor.on_end(child)
    processor.on_end(root)

    assert len(exporter.exports) == 1


def test_root_with_attributes_not_mapping_auto_generates_run_id():
    class SpanWithNonMappingAttrs:
        name = "ai.agent.run"
        parent = None
        span_id = 1
        scope_name = "lemma"
        attributes = 123
        _attrs: dict = None

        def __init__(self):
            self._attrs = {}

        @property
        def context(self):
            return _FakeSpanContext(span_id=self.span_id)

        @property
        def instrumentation_scope(self):
            return _FakeScope(name=self.scope_name)

        def set_attribute(self, key, value):
            self._attrs[key] = value

    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = SpanWithNonMappingAttrs()
    processor.on_start(root)
    assert "lemma.run_id" in root._attrs
    processor.on_end(root)


def test_span_with_instrumentation_scope_none_not_skipped():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": "run-s"},
    )
    child = _FakeSpan(
        name="child",
        span_id=2,
        parent=_FakeParent(span_id=1),
        instrumentation_scope_none=True,
    )

    processor.on_start(root)
    processor.on_start(child)
    processor.on_end(child)
    processor.on_end(root)

    assert len(exporter.exports) == 1
    assert len(exporter.exports[0]) == 2


def test_root_with_empty_lemma_run_id_auto_generates():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": ""},
    )

    processor.on_start(root)
    assert "lemma.run_id" in root.attributes
    assert len(root.attributes["lemma.run_id"]) > 0


def test_root_with_non_string_lemma_run_id_auto_generates():
    exporter = _FakeExporter()
    processor = RunBatchSpanProcessor(exporter)

    root = _FakeSpan(
        name="ai.agent.run",
        span_id=1,
        parent=None,
        attributes={"lemma.run_id": 123},
    )

    processor.on_start(root)
    assert "lemma.run_id" in root.attributes
    assert isinstance(root.attributes["lemma.run_id"], str)
