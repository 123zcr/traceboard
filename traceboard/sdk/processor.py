"""TraceBoardProcessor — core TracingProcessor implementation.

This processor captures traces and spans from the OpenAI Agents SDK
and writes them to a local SQLite database. All methods are synchronous
and thread-safe, as required by the TracingProcessor interface.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from agents.tracing.processor_interface import TracingProcessor

from traceboard.config import TraceboardConfig
from traceboard.cost import calculate_cost
from traceboard.server.database import SyncDatabase
from traceboard.server.models import SpanRecord, SpanType, TraceRecord, TraceStatus

logger = logging.getLogger("traceboard")

# Map OpenAI Agents SDK span data class names to our SpanType enum
_SPAN_TYPE_MAP: dict[str, SpanType] = {
    "AgentSpanData": SpanType.AGENT,
    "GenerationSpanData": SpanType.GENERATION,
    "FunctionSpanData": SpanType.FUNCTION,
    "GuardrailSpanData": SpanType.GUARDRAIL,
    "HandoffSpanData": SpanType.HANDOFF,
    "CustomSpanData": SpanType.CUSTOM,
    "TranscriptionSpanData": SpanType.TRANSCRIPTION,
    "SpeechSpanData": SpanType.SPEECH,
    "SpeechGroupSpanData": SpanType.SPEECH_GROUP,
}


class TraceBoardProcessor(TracingProcessor):
    """Captures OpenAI Agents SDK traces/spans and writes to local SQLite.

    Thread-safe. All callback methods are non-blocking (writes happen
    immediately via synchronous SQLite with WAL mode).
    """

    def __init__(self, config: TraceboardConfig | None = None):
        self.config = config or TraceboardConfig()
        self._db = SyncDatabase(self.config.db_path)
        self._db.connect()
        self._lock = threading.Lock()

        # Track token totals per trace for cost aggregation
        self._trace_tokens: dict[str, dict[str, int]] = {}
        self._trace_costs: dict[str, float] = {}

        logger.info(
            "TraceBoard initialized — traces will be saved to %s",
            self.config.db_path,
        )

    # ── TracingProcessor interface ─────────────────────────────────────

    def on_trace_start(self, trace: Any) -> None:
        """Called when a new trace begins."""
        try:
            trace_id = trace.trace_id
            workflow_name = getattr(trace, "name", None) or getattr(
                trace, "workflow_name", "Agent workflow"
            )
            group_id = getattr(trace, "group_id", None)
            metadata = getattr(trace, "metadata", None) or {}

            record = TraceRecord(
                trace_id=trace_id,
                workflow_name=workflow_name,
                group_id=group_id,
                started_at=time.time(),
                status=TraceStatus.RUNNING,
                metadata=metadata if isinstance(metadata, dict) else {},
            )

            with self._lock:
                self._trace_tokens[trace_id] = {"input": 0, "output": 0}
                self._trace_costs[trace_id] = 0.0
                self._db.insert_trace(record)

        except Exception:
            logger.exception("TraceBoard: error in on_trace_start")

    def on_trace_end(self, trace: Any) -> None:
        """Called when a trace completes."""
        try:
            trace_id = trace.trace_id

            with self._lock:
                tokens = self._trace_tokens.pop(trace_id, {"input": 0, "output": 0})
                total_cost = self._trace_costs.pop(trace_id, 0.0)
                total_tokens = tokens["input"] + tokens["output"]

                self._db.update_trace_end(
                    trace_id=trace_id,
                    ended_at=time.time(),
                    status=TraceStatus.COMPLETED.value,
                    total_tokens=total_tokens,
                    total_cost=total_cost,
                )

        except Exception:
            logger.exception("TraceBoard: error in on_trace_end")

    def on_span_start(self, span: Any) -> None:
        """Called when a new span begins."""
        try:
            span_data_obj = getattr(span, "span_data", None)
            span_type = self._resolve_span_type(span_data_obj)
            name = self._resolve_span_name(span, span_data_obj, span_type)

            record = SpanRecord(
                span_id=span.span_id,
                trace_id=span.trace_id,
                parent_id=getattr(span, "parent_id", None),
                span_type=span_type,
                name=name,
                started_at=time.time(),
            )

            with self._lock:
                self._db.insert_span(record)

        except Exception:
            logger.exception("TraceBoard: error in on_span_start")

    def on_span_end(self, span: Any) -> None:
        """Called when a span completes."""
        try:
            span_data_obj = getattr(span, "span_data", None)
            span_type = self._resolve_span_type(span_data_obj)
            span_data = self._extract_span_data(span_data_obj, span_type)
            error = self._extract_error(span)
            cost = 0.0

            # Calculate cost for generation spans
            if span_type == SpanType.GENERATION:
                cost = self._calculate_generation_cost(span_data)
                trace_id = span.trace_id
                with self._lock:
                    if trace_id in self._trace_costs:
                        self._trace_costs[trace_id] += cost
                    input_tokens = span_data.get("input_tokens", 0)
                    output_tokens = span_data.get("output_tokens", 0)
                    if trace_id in self._trace_tokens:
                        self._trace_tokens[trace_id]["input"] += input_tokens
                        self._trace_tokens[trace_id]["output"] += output_tokens

            with self._lock:
                self._db.update_span_end(
                    span_id=span.span_id,
                    ended_at=time.time(),
                    span_data=span_data,
                    error=error,
                    cost=cost,
                )

        except Exception:
            logger.exception("TraceBoard: error in on_span_end")

    def shutdown(self) -> None:
        """Clean up resources."""
        try:
            with self._lock:
                self._db.close()
            logger.info("TraceBoard shutdown complete.")
        except Exception:
            logger.exception("TraceBoard: error during shutdown")

    def force_flush(self) -> None:
        """Force flush — no-op since we write immediately."""
        pass

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _resolve_span_type(span_data: Any) -> SpanType:
        """Determine span type from the span_data object's class name."""
        if span_data is None:
            return SpanType.CUSTOM
        class_name = type(span_data).__name__
        return _SPAN_TYPE_MAP.get(class_name, SpanType.CUSTOM)

    @staticmethod
    def _resolve_span_name(span: Any, span_data: Any, span_type: SpanType) -> str:
        """Extract a human-readable name for the span."""
        # Try span.name first
        name = getattr(span, "name", None)
        if name:
            return str(name)

        # Try span_data-specific fields
        if span_data is not None:
            for attr in ("name", "agent_name", "function_name", "tool_name"):
                val = getattr(span_data, attr, None)
                if val:
                    return str(val)

        # Fallback to span type
        return span_type.value

    @staticmethod
    def _extract_span_data(span_data: Any, span_type: SpanType) -> dict[str, Any]:
        """Extract relevant data from the span_data object into a plain dict."""
        if span_data is None:
            return {}

        result: dict[str, Any] = {"type": span_type.value}

        if span_type == SpanType.GENERATION:
            # LLM generation data
            for attr in (
                "model",
                "model_config",
                "input",
                "output",
                "input_tokens",
                "output_tokens",
            ):
                val = getattr(span_data, attr, None)
                if val is not None:
                    result[attr] = _safe_serialize(val)

            # Usage from response
            usage = getattr(span_data, "usage", None)
            if usage:
                if hasattr(usage, "input_tokens"):
                    result["input_tokens"] = usage.input_tokens
                if hasattr(usage, "output_tokens"):
                    result["output_tokens"] = usage.output_tokens
                if hasattr(usage, "total_tokens"):
                    result["total_tokens"] = usage.total_tokens

        elif span_type == SpanType.FUNCTION:
            for attr in ("name", "input", "output"):
                val = getattr(span_data, attr, None)
                if val is not None:
                    result[attr] = _safe_serialize(val)

        elif span_type == SpanType.AGENT:
            for attr in ("name", "handoffs", "tools", "output_type"):
                val = getattr(span_data, attr, None)
                if val is not None:
                    result[attr] = _safe_serialize(val)

        elif span_type == SpanType.HANDOFF:
            for attr in ("from_agent", "to_agent"):
                val = getattr(span_data, attr, None)
                if val is not None:
                    result[attr] = _safe_serialize(val)

        elif span_type == SpanType.GUARDRAIL:
            for attr in ("name", "triggered"):
                val = getattr(span_data, attr, None)
                if val is not None:
                    result[attr] = _safe_serialize(val)

        else:
            # Generic: try to capture any public attributes
            for attr in dir(span_data):
                if not attr.startswith("_"):
                    try:
                        val = getattr(span_data, attr)
                        if not callable(val):
                            result[attr] = _safe_serialize(val)
                    except Exception:
                        pass

        return result

    @staticmethod
    def _extract_error(span: Any) -> dict[str, Any] | None:
        """Extract error information from a span, if any."""
        error = getattr(span, "error", None)
        if error is None:
            return None
        if isinstance(error, dict):
            return error
        if isinstance(error, Exception):
            return {"type": type(error).__name__, "message": str(error)}
        return {"message": str(error)}

    @staticmethod
    def _calculate_generation_cost(span_data: dict[str, Any]) -> float:
        """Calculate cost from generation span data."""
        model = span_data.get("model", "")
        input_tokens = span_data.get("input_tokens", 0) or 0
        output_tokens = span_data.get("output_tokens", 0) or 0
        if model and (input_tokens or output_tokens):
            return calculate_cost(model, input_tokens, output_tokens)
        return 0.0


def _safe_serialize(value: Any) -> Any:
    """Safely convert a value to a JSON-serializable form."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in value.items()}
    # Try common serialization methods
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return {k: _safe_serialize(v) for k, v in value.__dict__.items() if not k.startswith("_")}
    return str(value)
