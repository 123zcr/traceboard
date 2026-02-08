"""Pydantic models for TraceBoard API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────


class TraceStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class SpanType(str, Enum):
    AGENT = "agent"
    GENERATION = "generation"
    FUNCTION = "function"
    GUARDRAIL = "guardrail"
    HANDOFF = "handoff"
    CUSTOM = "custom"
    TRANSCRIPTION = "transcription"
    SPEECH = "speech"
    SPEECH_GROUP = "speech_group"


# ── Trace Models ───────────────────────────────────────────────────────────


class TraceRecord(BaseModel):
    trace_id: str
    workflow_name: str = ""
    group_id: str | None = None
    started_at: float
    ended_at: float | None = None
    status: TraceStatus = TraceStatus.RUNNING
    metadata: dict[str, Any] = Field(default_factory=dict)
    total_tokens: int = 0
    total_cost: float = 0.0


class TraceListItem(BaseModel):
    trace_id: str
    workflow_name: str
    group_id: str | None = None
    started_at: float
    ended_at: float | None = None
    status: TraceStatus
    total_tokens: int
    total_cost: float
    duration_ms: float | None = None
    span_count: int = 0


class TraceListResponse(BaseModel):
    traces: list[TraceListItem]
    total: int
    page: int
    page_size: int


# ── Span Models ────────────────────────────────────────────────────────────


class SpanRecord(BaseModel):
    span_id: str
    trace_id: str
    parent_id: str | None = None
    span_type: SpanType = SpanType.CUSTOM
    name: str = ""
    started_at: float
    ended_at: float | None = None
    span_data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    cost: float = 0.0


class SpanTreeNode(BaseModel):
    span_id: str
    trace_id: str
    parent_id: str | None = None
    span_type: SpanType
    name: str
    started_at: float
    ended_at: float | None = None
    span_data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    cost: float = 0.0
    duration_ms: float | None = None
    children: list[SpanTreeNode] = Field(default_factory=list)


class TraceDetailResponse(BaseModel):
    trace: TraceRecord
    spans: list[SpanRecord]
    tree: list[SpanTreeNode]


# ── Metrics Models ─────────────────────────────────────────────────────────


class MetricsResponse(BaseModel):
    total_traces: int = 0
    total_spans: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    avg_duration_ms: float = 0.0
    error_count: int = 0
    traces_by_status: dict[str, int] = Field(default_factory=dict)
    cost_by_model: dict[str, float] = Field(default_factory=dict)


# ── WebSocket Event Models ─────────────────────────────────────────────────


class LiveEvent(BaseModel):
    event_type: str
    data: dict[str, Any]
