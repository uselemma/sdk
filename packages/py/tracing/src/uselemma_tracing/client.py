from __future__ import annotations

import contextvars
import inspect
import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypedDict, TypeVar

from .debug_mode import _lemma_debug

T = TypeVar("T")
SpanType = Literal["span", "generation", "tool"]
Status = Literal["OK", "ERROR"]

_active_trace: contextvars.ContextVar["TraceContext | None"] = contextvars.ContextVar(
    "lemma_active_trace",
    default=None,
)


class Usage(TypedDict, total=False):
    input_tokens: int
    output_tokens: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat().replace("+00:00", "Z")


def _error_message(error: Any) -> str | None:
    if error is None:
        return None
    if isinstance(error, BaseException):
        return str(error)
    return str(error)


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _duration_ms(
    start: datetime | str | None, end: datetime | str | None
) -> int | None:
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _serialize_attribute(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    try:
        return json.dumps(value, separators=(",", ":"))
    except TypeError:
        return str(value)


def _add_defined(attributes: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        attributes[key] = value


def _flatten_message(attributes: dict[str, Any], prefix: str, message: Any) -> None:
    if isinstance(message, dict):
        for key, value in message.items():
            _add_defined(
                attributes, f"{prefix}.message.{key}", _serialize_attribute(value)
            )
        return
    _add_defined(attributes, f"{prefix}.message.content", _serialize_attribute(message))


def _flatten_document(attributes: dict[str, Any], prefix: str, document: Any) -> None:
    if isinstance(document, dict):
        for key, value in document.items():
            _add_defined(
                attributes, f"{prefix}.document.{key}", _serialize_attribute(value)
            )
        return
    _add_defined(
        attributes, f"{prefix}.document.content", _serialize_attribute(document)
    )


def _span_attributes(
    attributes: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    usage: Usage | None = None,
    input_mime_type: str | None = None,
    output_mime_type: str | None = None,
    llm_model_name: str | None = None,
    llm_provider: str | None = None,
    llm_system: str | None = None,
    llm_invocation_parameters: Any = None,
    llm_input_messages: list[Any] | None = None,
    llm_output_messages: list[Any] | None = None,
    llm_tools: Any = None,
    llm_token_count_prompt: int | None = None,
    llm_token_count_completion: int | None = None,
    llm_token_count_total: int | None = None,
    llm_prompt_template: str | None = None,
    llm_prompt_template_variables: Any = None,
    llm_prompt_template_version: str | None = None,
    tool_description: str | None = None,
    tool_parameters: Any = None,
    retrieval_documents: list[Any] | None = None,
    embedding_model_name: str | None = None,
    embedding_invocation_parameters: Any = None,
    embedding_embeddings: Any = None,
    reranker_model_name: str | None = None,
    reranker_input_documents: list[Any] | None = None,
    reranker_output_documents: list[Any] | None = None,
) -> dict[str, Any] | None:
    attrs = dict(attributes or {})
    _add_defined(attrs, "input.mime_type", input_mime_type)
    _add_defined(attrs, "output.mime_type", output_mime_type)
    _add_defined(attrs, "llm.model_name", llm_model_name or model)
    _add_defined(attrs, "llm.provider", llm_provider)
    _add_defined(attrs, "llm.system", llm_system)
    _add_defined(
        attrs,
        "llm.invocation_parameters",
        _serialize_attribute(llm_invocation_parameters),
    )
    _add_defined(attrs, "llm.tools", _serialize_attribute(llm_tools))
    _add_defined(
        attrs,
        "llm.token_count.prompt",
        llm_token_count_prompt
        if llm_token_count_prompt is not None
        else (usage or {}).get("input_tokens"),
    )
    _add_defined(
        attrs,
        "llm.token_count.completion",
        llm_token_count_completion
        if llm_token_count_completion is not None
        else (usage or {}).get("output_tokens"),
    )
    _add_defined(attrs, "llm.token_count.total", llm_token_count_total)
    _add_defined(attrs, "llm.prompt_template.template", llm_prompt_template)
    _add_defined(
        attrs,
        "llm.prompt_template.variables",
        _serialize_attribute(llm_prompt_template_variables),
    )
    _add_defined(attrs, "llm.prompt_template.version", llm_prompt_template_version)
    _add_defined(attrs, "tool.description", tool_description)
    _add_defined(attrs, "tool.parameters", _serialize_attribute(tool_parameters))
    _add_defined(attrs, "embedding.model_name", embedding_model_name)
    _add_defined(
        attrs,
        "embedding.invocation_parameters",
        _serialize_attribute(embedding_invocation_parameters),
    )
    _add_defined(
        attrs, "embedding.embeddings", _serialize_attribute(embedding_embeddings)
    )
    _add_defined(attrs, "reranker.model_name", reranker_model_name)
    for index, message in enumerate(llm_input_messages or []):
        _flatten_message(attrs, f"llm.input_messages.{index}", message)
    for index, message in enumerate(llm_output_messages or []):
        _flatten_message(attrs, f"llm.output_messages.{index}", message)
    for index, document in enumerate(retrieval_documents or []):
        _flatten_document(attrs, f"retrieval.documents.{index}", document)
    for index, document in enumerate(reranker_input_documents or []):
        _flatten_document(attrs, f"reranker.input_documents.{index}", document)
    for index, document in enumerate(reranker_output_documents or []):
        _flatten_document(attrs, f"reranker.output_documents.{index}", document)
    return attrs or None


@dataclass
class SpanHandle:
    trace: "TraceContext"
    name: str
    input: Any = None
    metadata: dict[str, Any] | None = None
    type: SpanType = "span"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=_now)
    ended: bool = False

    def end(
        self,
        *,
        output: Any = None,
        duration_ms: int | None = None,
        status: Status | None = None,
        error: Any = None,
        metadata: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        input_mime_type: str | None = None,
        output_mime_type: str | None = None,
        retrieval_documents: list[Any] | None = None,
        embedding_model_name: str | None = None,
        embedding_invocation_parameters: Any = None,
        embedding_embeddings: Any = None,
        reranker_model_name: str | None = None,
        reranker_input_documents: list[Any] | None = None,
        reranker_output_documents: list[Any] | None = None,
    ) -> None:
        if self.ended:
            return
        self.ended = True
        self.trace.record_span(
            name=self.name,
            input=self.input,
            output=output,
            metadata=metadata or self.metadata,
            attributes=attributes,
            input_mime_type=input_mime_type,
            output_mime_type=output_mime_type,
            retrieval_documents=retrieval_documents,
            embedding_model_name=embedding_model_name,
            embedding_invocation_parameters=embedding_invocation_parameters,
            embedding_embeddings=embedding_embeddings,
            reranker_model_name=reranker_model_name,
            reranker_input_documents=reranker_input_documents,
            reranker_output_documents=reranker_output_documents,
            status=status,
            error=error,
            id=self.id,
            started_at=self.started_at,
            ended_at=_now(),
            duration_ms=duration_ms,
            type=self.type,
        )


@dataclass
class TraceContext:
    name: str
    input: Any = None
    metadata: dict[str, Any] | None = None
    thread_id: str | None = None
    user_id: str | None = None
    environment: str | None = None
    duration_ms: int | None = None
    output_value: Any = None
    error: str | None = None
    spans: list[dict[str, Any]] = field(default_factory=list)

    def output(self, value: Any) -> None:
        self.output_value = value

    def fail(self, error: Any) -> None:
        self.error = _error_message(error)

    def span(
        self,
        *,
        name: str,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        input_mime_type: str | None = None,
        output_mime_type: str | None = None,
        retrieval_documents: list[Any] | None = None,
        embedding_model_name: str | None = None,
        embedding_invocation_parameters: Any = None,
        embedding_embeddings: Any = None,
        reranker_model_name: str | None = None,
        reranker_input_documents: list[Any] | None = None,
        reranker_output_documents: list[Any] | None = None,
        started_at: datetime | str | None = None,
        ended_at: datetime | str | None = None,
        duration_ms: int | None = None,
        status: Status | None = None,
        error: Any = None,
        id: str | None = None,
        parent_id: str | None = None,
        type: SpanType = "span",
    ) -> None:
        started = started_at or _now()
        ended = ended_at or _now()
        self.spans.append(
            _compact(
                {
                    "id": id,
                    "parent_id": parent_id,
                    "name": name,
                    "type": type,
                    "input": input,
                    "output": output,
                    "metadata": metadata,
                    "attributes": _span_attributes(
                        attributes,
                        input_mime_type=input_mime_type,
                        output_mime_type=output_mime_type,
                        retrieval_documents=retrieval_documents,
                        embedding_model_name=embedding_model_name,
                        embedding_invocation_parameters=embedding_invocation_parameters,
                        embedding_embeddings=embedding_embeddings,
                        reranker_model_name=reranker_model_name,
                        reranker_input_documents=reranker_input_documents,
                        reranker_output_documents=reranker_output_documents,
                    ),
                    "started_at": _iso(started),
                    "ended_at": _iso(ended),
                    "duration_ms": duration_ms,
                    "status": status or ("ERROR" if error else None),
                    "error": _error_message(error),
                }
            )
        )

    record_span = span

    def generation(
        self,
        *,
        name: str,
        input: Any = None,
        output: Any = None,
        model: str | None = None,
        usage: Usage | None = None,
        metadata: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        input_mime_type: str | None = None,
        output_mime_type: str | None = None,
        llm_model_name: str | None = None,
        llm_provider: str | None = None,
        llm_system: str | None = None,
        llm_invocation_parameters: Any = None,
        llm_input_messages: list[Any] | None = None,
        llm_output_messages: list[Any] | None = None,
        llm_tools: Any = None,
        llm_token_count_prompt: int | None = None,
        llm_token_count_completion: int | None = None,
        llm_token_count_total: int | None = None,
        llm_prompt_template: str | None = None,
        llm_prompt_template_variables: Any = None,
        llm_prompt_template_version: str | None = None,
        duration_ms: int | None = None,
        status: Status | None = None,
        error: Any = None,
    ) -> None:
        now = _now()
        self.spans.append(
            _compact(
                {
                    "name": name,
                    "type": "generation",
                    "input": input,
                    "output": output,
                    "model": model,
                    "usage": usage,
                    "metadata": metadata,
                    "attributes": _span_attributes(
                        attributes,
                        model=model,
                        usage=usage,
                        input_mime_type=input_mime_type,
                        output_mime_type=output_mime_type,
                        llm_model_name=llm_model_name,
                        llm_provider=llm_provider,
                        llm_system=llm_system,
                        llm_invocation_parameters=llm_invocation_parameters,
                        llm_input_messages=llm_input_messages,
                        llm_output_messages=llm_output_messages,
                        llm_tools=llm_tools,
                        llm_token_count_prompt=llm_token_count_prompt,
                        llm_token_count_completion=llm_token_count_completion,
                        llm_token_count_total=llm_token_count_total,
                        llm_prompt_template=llm_prompt_template,
                        llm_prompt_template_variables=llm_prompt_template_variables,
                        llm_prompt_template_version=llm_prompt_template_version,
                    ),
                    "duration_ms": duration_ms,
                    "status": status or ("ERROR" if error else None),
                    "error": _error_message(error),
                    "started_at": _iso(now),
                    "ended_at": _iso(now),
                }
            )
        )

    record_generation = generation

    def tool(
        self,
        *,
        name: str,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        input_mime_type: str | None = None,
        output_mime_type: str | None = None,
        tool_description: str | None = None,
        tool_parameters: Any = None,
        duration_ms: int | None = None,
        status: Status | None = None,
        error: Any = None,
    ) -> None:
        now = _now()
        self.spans.append(
            _compact(
                {
                    "name": name,
                    "type": "tool",
                    "input": input,
                    "output": output,
                    "metadata": metadata,
                    "attributes": _span_attributes(
                        attributes,
                        input_mime_type=input_mime_type,
                        output_mime_type=output_mime_type,
                        tool_description=tool_description,
                        tool_parameters=tool_parameters,
                    ),
                    "duration_ms": duration_ms,
                    "status": status or ("ERROR" if error else None),
                    "error": _error_message(error),
                    "started_at": _iso(now),
                    "ended_at": _iso(now),
                }
            )
        )

    record_tool = tool

    def start_span(
        self,
        *,
        name: str,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanHandle:
        return SpanHandle(trace=self, name=name, input=input, metadata=metadata)

    def start_generation(
        self,
        *,
        name: str,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanHandle:
        return SpanHandle(
            trace=self,
            name=name,
            input=input,
            metadata=metadata,
            type="generation",
        )

    def start_tool(
        self,
        *,
        name: str,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanHandle:
        return SpanHandle(
            trace=self,
            name=name,
            input=input,
            metadata=metadata,
            type="tool",
        )

    def payload(
        self, project_id: str, started_at: datetime, ended_at: datetime
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "trace": {
                "name": self.name,
                "input": self.input,
                "output": self.output_value,
                "metadata": self.metadata,
                "thread_id": self.thread_id,
                "user_id": self.user_id,
                "environment": self.environment,
                "started_at": _iso(started_at),
                "ended_at": _iso(ended_at),
                "duration_ms": self.duration_ms
                if self.duration_ms is not None
                else _duration_ms(started_at, ended_at),
                "status": "ERROR" if self.error else None,
                "error": self.error,
                "spans": self.spans,
            },
        }


class Lemma:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        project_id: str | None = None,
        base_url: str = "https://api.uselemma.ai",
        transport: Callable[[str, dict[str, str], bytes], tuple[int, str]]
        | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("LEMMA_API_KEY")
        self.project_id = project_id or os.environ.get("LEMMA_PROJECT_ID")
        if not self.api_key:
            raise ValueError("uselemma-tracing: Missing LEMMA_API_KEY")
        if not self.project_id:
            raise ValueError("uselemma-tracing: Missing LEMMA_PROJECT_ID")
        self.base_url = base_url.rstrip("/")
        self.transport = transport or self._urllib_transport

    def trace(
        self,
        name: str,
        fn: Callable[[TraceContext], T],
        *,
        input: Any = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        environment: str | None = None,
        duration_ms: int | None = None,
    ) -> T:
        ctx = TraceContext(
            name=name,
            input=input,
            metadata=metadata,
            thread_id=thread_id,
            user_id=user_id,
            environment=environment,
            duration_ms=duration_ms,
        )
        started_at = _now()
        _lemma_debug("client", "trace started", name=ctx.name)
        token = _active_trace.set(ctx)
        try:
            result = fn(ctx)
            if ctx.output_value is None:
                ctx.output(result)
            self._send(ctx, started_at, _now())
            return result
        except BaseException as exc:
            ctx.fail(exc)
            self._send(ctx, started_at, _now())
            raise
        finally:
            _active_trace.reset(token)

    async def async_trace(
        self,
        name: str,
        fn: Callable[[TraceContext], T],
        *,
        input: Any = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        environment: str | None = None,
        duration_ms: int | None = None,
    ) -> T:
        ctx = TraceContext(
            name=name,
            input=input,
            metadata=metadata,
            thread_id=thread_id,
            user_id=user_id,
            environment=environment,
            duration_ms=duration_ms,
        )
        started_at = _now()
        _lemma_debug("client", "trace started", name=ctx.name)
        token = _active_trace.set(ctx)
        try:
            maybe_result = fn(ctx)
            result = (
                await maybe_result
                if inspect.isawaitable(maybe_result)
                else maybe_result
            )
            if ctx.output_value is None:
                ctx.output(result)
            self._send(ctx, started_at, _now())
            return result
        except BaseException as exc:
            ctx.fail(exc)
            self._send(ctx, started_at, _now())
            raise
        finally:
            _active_trace.reset(token)

    def _send(
        self, ctx: TraceContext, started_at: datetime, ended_at: datetime
    ) -> None:
        payload = ctx.payload(self.project_id or "", started_at, ended_at)
        body = json.dumps(payload, default=str).encode()
        url = f"{self.base_url}/traces/ingest"
        _lemma_debug(
            "client",
            "sending trace",
            name=payload["trace"]["name"],
            span_count=len(payload["trace"]["spans"]),
            url=url,
        )
        status, text = self.transport(
            url,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            body,
        )
        if status < 200 or status >= 300:
            _lemma_debug("client", "trace ingest failed", status=status, body=text)
            raise RuntimeError(
                f"uselemma-tracing: failed to ingest trace ({status}): {text}"
            )
        _lemma_debug("client", "trace sent", status=status)

    @staticmethod
    def _urllib_transport(
        url: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, str]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()


def active() -> TraceContext:
    ctx = _active_trace.get()
    if ctx is None:
        raise RuntimeError("uselemma-tracing: no active trace context")
    return ctx
