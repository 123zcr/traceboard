"""Span API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from traceboard.server.models import SpanRecord, SpanTreeNode

router = APIRouter(tags=["spans"])


def _get_db(request: Request):
    return request.app.state.db


@router.get("/traces/{trace_id}/spans", response_model=list[SpanRecord])
async def get_spans(request: Request, trace_id: str):
    """Get all spans for a trace (flat list, ordered by start time)."""
    db = _get_db(request)
    return await db.get_spans_for_trace(trace_id)


@router.get("/traces/{trace_id}/tree", response_model=list[SpanTreeNode])
async def get_span_tree(request: Request, trace_id: str):
    """Get spans as a nested tree structure for timeline rendering."""
    db = _get_db(request)
    return await db.build_span_tree(trace_id)
