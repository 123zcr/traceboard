"""BaseTracer — shared trace/span recording logic for all SDK adapters.

Each adapter (OpenAI, Anthropic, LangChain, LiteLLM) inherits from
BaseTracer and uses its ``record_llm_start`` / ``record_llm_end``
helpers to write TraceRecord + SpanRecord into the shared SQLite
database.  The dashboard, API, and exporter work unchanged regardless
of which adapter produced the data.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from traceboard.config import TraceboardConfig
from traceboard.cost import calculate_cost
from traceboard.server.database import SyncDatabase
from traceboard.server.models import SpanRecord, SpanType, TraceRecord, TraceStatus

logger = logging.getLogger("traceboard")


class BaseTracer:
    """Thread-safe base class that writes traces and spans to SQLite.

    Subclasses only need to call :meth:`record_llm_start` when an LLM
    call begins and :meth:`record_llm_end` when it completes.  All
    database operations, cost calculation, and token aggregation are
    handled here.
    """

    def __init__(self, config: TraceboardConfig | None = None):
        self.config = config or TraceboardConfig()
        self._db = SyncDatabase(self.config.db_path)
        self._db.connect()
        self._lock = threading.Lock()

    # ── Public helpers for subclasses ──────────────────────────────────

    @staticmethod
    def _generate_id(prefix: str = "tb") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def record_llm_start(
        self,
        *,
        trace_id: str | None = None,
        span_id: str | None = None,
        workflow_name: str = "LLM Call",
        model: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Record the start of an LLM call.

        Returns:
            ``(trace_id, span_id)`` for use in :meth:`record_llm_end`.
        """
        trace_id = trace_id or self._generate_id("trace")
        span_id = span_id or self._generate_id("span")
        now = time.time()

        trace = TraceRecord(
            trace_id=trace_id,
            workflow_name=workflow_name,
            started_at=now,
            status=TraceStatus.RUNNING,
            metadata=metadata or {},
        )
        span = SpanRecord(
            span_id=span_id,
            trace_id=trace_id,
            span_type=SpanType.GENERATION,
            name=model or workflow_name,
            started_at=now,
        )

        try:
            with self._lock:
                self._db.insert_trace(trace)
                self._db.insert_span(span)
        except Exception:
            logger.exception("TraceBoard: error in record_llm_start")

        return trace_id, span_id

    def record_llm_end(
        self,
        *,
        trace_id: str,
        span_id: str,
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        response_text: str | None = None,
        error: dict[str, Any] | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        """Record the completion of an LLM call."""
        now = time.time()
        total_tokens = input_tokens + output_tokens
        cost = calculate_cost(model, input_tokens, output_tokens) if model else 0.0

        span_data: dict[str, Any] = {
            "type": SpanType.GENERATION.value,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        if response_text is not None:
            span_data["output"] = (
                response_text[:2000] if len(response_text) > 2000 else response_text
            )
        if extra_data:
            span_data.update(extra_data)

        status = TraceStatus.ERROR.value if error else TraceStatus.COMPLETED.value

        try:
            with self._lock:
                self._db.update_span_end(
                    span_id=span_id,
                    ended_at=now,
                    span_data=span_data,
                    error=error,
                    cost=cost,
                )
                self._db.update_trace_end(
                    trace_id=trace_id,
                    ended_at=now,
                    status=status,
                    total_tokens=total_tokens,
                    total_cost=cost,
                )
        except Exception:
            logger.exception("TraceBoard: error in record_llm_end")

    def record_tool_call(
        self,
        *,
        trace_id: str,
        tool_name: str,
        tool_input: str = "",
        tool_output: str = "",
        parent_span_id: str | None = None,
        started_at: float | None = None,
        ended_at: float | None = None,
    ) -> str:
        """Record a tool/function call as a child span."""
        span_id = self._generate_id("span")
        now = time.time()
        start = started_at or now
        end = ended_at or now

        span = SpanRecord(
            span_id=span_id,
            trace_id=trace_id,
            parent_id=parent_span_id,
            span_type=SpanType.FUNCTION,
            name=tool_name,
            started_at=start,
            ended_at=end,
            span_data={
                "type": SpanType.FUNCTION.value,
                "name": tool_name,
                "input": tool_input[:2000] if len(tool_input) > 2000 else tool_input,
                "output": tool_output[:2000] if len(tool_output) > 2000 else tool_output,
            },
        )

        try:
            with self._lock:
                self._db.insert_span(span)
        except Exception:
            logger.exception("TraceBoard: error in record_tool_call")

        return span_id

    def shutdown(self) -> None:
        """Close the database connection."""
        try:
            with self._lock:
                self._db.close()
        except Exception:
            logger.exception("TraceBoard: error during shutdown")
