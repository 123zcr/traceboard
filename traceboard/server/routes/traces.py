"""Trace API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Query

from traceboard.server.models import (
    TraceDetailResponse,
    TraceListResponse,
)

router = APIRouter(tags=["traces"])


def _get_db(request: Request):
    return request.app.state.db


@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    status: str | None = Query(None, description="Filter by status"),
    workflow_name: str | None = Query(None, description="Filter by workflow name"),
):
    """List all traces with pagination and optional filters."""
    db = _get_db(request)
    items, total = await db.list_traces(
        page=page, page_size=page_size, status=status, workflow_name=workflow_name,
    )
    return TraceListResponse(traces=items, total=total, page=page, page_size=page_size)


@router.get("/traces/{trace_id}")
async def get_trace_detail(request: Request, trace_id: str):
    """Get full trace details with all spans and span tree."""
    db = _get_db(request)
    trace = await db.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    spans = await db.get_spans_for_trace(trace_id)
    tree = await db.build_span_tree(trace_id)
    return TraceDetailResponse(trace=trace, spans=spans, tree=tree)


@router.delete("/traces")
async def delete_all_traces(request: Request):
    """Delete all traces and spans."""
    db = _get_db(request)
    count = await db.delete_all()
    return {"deleted": count, "message": f"Deleted {count} traces"}


@router.get("/traces/{trace_id}/export")
async def export_trace(request: Request, trace_id: str):
    """Export a single trace with all its spans."""
    db = _get_db(request)
    trace = await db.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    spans = await db.get_spans_for_trace(trace_id)
    return {"trace": trace.model_dump(), "spans": [s.model_dump() for s in spans]}
