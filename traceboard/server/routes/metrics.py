"""Metrics API routes with WebSocket live updates."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from traceboard.server.models import MetricsResponse

logger = logging.getLogger("traceboard")

router = APIRouter(tags=["metrics"])


def _get_db(request: Request):
    return request.app.state.db


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(request: Request):
    """Get aggregated metrics across all traces."""
    db = _get_db(request)
    return await db.get_metrics()


@router.get("/export")
async def export_all(request: Request):
    """Export all traces and spans as JSON."""
    db = _get_db(request)
    return await db.export_all()


# ── WebSocket for live updates ─────────────────────────────────────────


class ConnectionManager:
    """Manages active WebSocket connections for live updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for ws in dead:
            if ws in self.active_connections:
                self.active_connections.remove(ws)

    @property
    def has_connections(self) -> bool:
        return len(self.active_connections) > 0


manager = ConnectionManager()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """WebSocket endpoint for real-time trace/span events."""
    await manager.connect(websocket)
    db = websocket.app.state.db

    async def push_updates():
        """Background task: poll DB and push updates on change."""
        last_trace_count = -1
        last_span_count = -1
        try:
            while True:
                await asyncio.sleep(1)
                try:
                    metrics = await db.get_metrics()
                except Exception:
                    logger.debug("WebSocket push: failed to read metrics")
                    continue

                tc = metrics.total_traces
                sc = metrics.total_spans

                if tc != last_trace_count or sc != last_span_count:
                    last_trace_count = tc
                    last_span_count = sc
                    try:
                        await websocket.send_json({
                            "type": "update",
                            "metrics": metrics.model_dump(),
                        })
                    except Exception:
                        break
        except asyncio.CancelledError:
            pass

    push_task = asyncio.create_task(push_updates())
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket connection error")
    finally:
        push_task.cancel()
        try:
            await push_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(websocket)
