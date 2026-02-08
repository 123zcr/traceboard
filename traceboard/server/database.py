"""SQLite database operations for TraceBoard."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from traceboard.server.models import (
    MetricsResponse,
    SpanRecord,
    SpanTreeNode,
    TraceListItem,
    TraceRecord,
    TraceStatus,
)

# ── Schema ─────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id       TEXT PRIMARY KEY,
    workflow_name  TEXT NOT NULL DEFAULT '',
    group_id       TEXT,
    started_at     REAL NOT NULL,
    ended_at       REAL,
    status         TEXT NOT NULL DEFAULT 'running',
    metadata       TEXT NOT NULL DEFAULT '{}',
    total_tokens   INTEGER NOT NULL DEFAULT 0,
    total_cost     REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS spans (
    span_id    TEXT PRIMARY KEY,
    trace_id   TEXT NOT NULL,
    parent_id  TEXT,
    span_type  TEXT NOT NULL DEFAULT 'custom',
    name       TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    ended_at   REAL,
    span_data  TEXT NOT NULL DEFAULT '{}',
    error      TEXT,
    cost       REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_parent_id ON spans(parent_id);
CREATE INDEX IF NOT EXISTS idx_traces_started_at ON traces(started_at);
CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status);
"""


class Database:
    """Async SQLite database wrapper for TraceBoard."""

    def __init__(self, db_path: str = "./traceboard.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and ensure schema exists."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # ── Trace operations ───────────────────────────────────────────────

    async def insert_trace(self, trace: TraceRecord) -> None:
        """Insert or replace a trace record."""
        await self.db.execute(
            """INSERT OR REPLACE INTO traces
               (trace_id, workflow_name, group_id, started_at, ended_at,
                status, metadata, total_tokens, total_cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace.trace_id,
                trace.workflow_name,
                trace.group_id,
                trace.started_at,
                trace.ended_at,
                trace.status.value,
                json.dumps(trace.metadata),
                trace.total_tokens,
                trace.total_cost,
            ),
        )
        await self.db.commit()

    async def update_trace(self, trace: TraceRecord) -> None:
        """Update an existing trace record."""
        await self.db.execute(
            """UPDATE traces SET
               workflow_name=?, group_id=?, ended_at=?, status=?,
               metadata=?, total_tokens=?, total_cost=?
               WHERE trace_id=?""",
            (
                trace.workflow_name,
                trace.group_id,
                trace.ended_at,
                trace.status.value,
                json.dumps(trace.metadata),
                trace.total_tokens,
                trace.total_cost,
                trace.trace_id,
            ),
        )
        await self.db.commit()

    async def get_trace(self, trace_id: str) -> TraceRecord | None:
        """Get a single trace by ID."""
        async with self.db.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_trace(row)

    async def list_traces(
        self,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        workflow_name: str | None = None,
    ) -> tuple[list[TraceListItem], int]:
        """List traces with pagination and optional filters."""
        where_parts: list[str] = []
        params: list[Any] = []

        if status:
            where_parts.append("t.status = ?")
            params.append(status)
        if workflow_name:
            where_parts.append("t.workflow_name LIKE ?")
            params.append(f"%{workflow_name}%")

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # Count total
        count_sql = f"SELECT COUNT(*) FROM traces t {where_clause}"
        async with self.db.execute(count_sql, params) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        # Fetch page
        offset = (page - 1) * page_size
        query_sql = f"""
            SELECT t.*,
                   COUNT(s.span_id) as span_count
            FROM traces t
            LEFT JOIN spans s ON s.trace_id = t.trace_id
            {where_clause}
            GROUP BY t.trace_id
            ORDER BY t.started_at DESC
            LIMIT ? OFFSET ?
        """
        query_params = params + [page_size, offset]

        items: list[TraceListItem] = []
        async with self.db.execute(query_sql, query_params) as cursor:
            async for row in cursor:
                started = row["started_at"]
                ended = row["ended_at"]
                duration = (ended - started) * 1000 if ended else None
                items.append(
                    TraceListItem(
                        trace_id=row["trace_id"],
                        workflow_name=row["workflow_name"],
                        group_id=row["group_id"],
                        started_at=started,
                        ended_at=ended,
                        status=TraceStatus(row["status"]),
                        total_tokens=row["total_tokens"],
                        total_cost=row["total_cost"],
                        duration_ms=duration,
                        span_count=row["span_count"],
                    )
                )
        return items, total

    # ── Span operations ────────────────────────────────────────────────

    async def insert_span(self, span: SpanRecord) -> None:
        """Insert or replace a span record."""
        await self.db.execute(
            """INSERT OR REPLACE INTO spans
               (span_id, trace_id, parent_id, span_type, name,
                started_at, ended_at, span_data, error, cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                span.span_id,
                span.trace_id,
                span.parent_id,
                span.span_type.value,
                span.name,
                span.started_at,
                span.ended_at,
                json.dumps(span.span_data),
                json.dumps(span.error) if span.error else None,
                span.cost,
            ),
        )
        await self.db.commit()

    async def update_span(self, span: SpanRecord) -> None:
        """Update an existing span record."""
        await self.db.execute(
            """UPDATE spans SET
               ended_at=?, span_data=?, error=?, cost=?
               WHERE span_id=?""",
            (
                span.ended_at,
                json.dumps(span.span_data),
                json.dumps(span.error) if span.error else None,
                span.cost,
                span.span_id,
            ),
        )
        await self.db.commit()

    async def get_spans_for_trace(self, trace_id: str) -> list[SpanRecord]:
        """Get all spans belonging to a trace."""
        spans: list[SpanRecord] = []
        async with self.db.execute(
            "SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at ASC",
            (trace_id,),
        ) as cursor:
            async for row in cursor:
                spans.append(self._row_to_span(row))
        return spans

    async def build_span_tree(self, trace_id: str) -> list[SpanTreeNode]:
        """Build a tree of spans for a trace."""
        spans = await self.get_spans_for_trace(trace_id)

        nodes: dict[str, SpanTreeNode] = {}
        for s in spans:
            duration = (s.ended_at - s.started_at) * 1000 if s.ended_at else None
            nodes[s.span_id] = SpanTreeNode(
                span_id=s.span_id,
                trace_id=s.trace_id,
                parent_id=s.parent_id,
                span_type=s.span_type,
                name=s.name,
                started_at=s.started_at,
                ended_at=s.ended_at,
                span_data=s.span_data,
                error=s.error,
                cost=s.cost,
                duration_ms=duration,
                children=[],
            )

        roots: list[SpanTreeNode] = []
        for node in nodes.values():
            if node.parent_id and node.parent_id in nodes:
                nodes[node.parent_id].children.append(node)
            else:
                roots.append(node)

        return roots

    # ── Metrics ────────────────────────────────────────────────────────

    async def get_metrics(self) -> MetricsResponse:
        """Compute aggregated metrics from all traces."""
        metrics = MetricsResponse()

        async with self.db.execute("SELECT COUNT(*) FROM traces") as cur:
            row = await cur.fetchone()
            metrics.total_traces = row[0] if row else 0

        async with self.db.execute("SELECT COUNT(*) FROM spans") as cur:
            row = await cur.fetchone()
            metrics.total_spans = row[0] if row else 0

        async with self.db.execute(
            "SELECT COALESCE(SUM(total_tokens),0), COALESCE(SUM(total_cost),0) FROM traces"
        ) as cur:
            row = await cur.fetchone()
            if row:
                metrics.total_tokens = int(row[0])
                metrics.total_cost = float(row[1])

        async with self.db.execute(
            """SELECT AVG((ended_at - started_at) * 1000)
               FROM traces WHERE ended_at IS NOT NULL"""
        ) as cur:
            row = await cur.fetchone()
            if row and row[0] is not None:
                metrics.avg_duration_ms = round(float(row[0]), 2)

        async with self.db.execute(
            "SELECT COUNT(*) FROM traces WHERE status = 'error'"
        ) as cur:
            row = await cur.fetchone()
            metrics.error_count = row[0] if row else 0

        async with self.db.execute(
            "SELECT status, COUNT(*) FROM traces GROUP BY status"
        ) as cur:
            async for row in cur:
                metrics.traces_by_status[row[0]] = row[1]

        async with self.db.execute(
            "SELECT span_data, cost FROM spans WHERE span_type = 'generation' AND cost > 0"
        ) as cur:
            async for row in cur:
                try:
                    data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    model = data.get("model", "unknown")
                    metrics.cost_by_model[model] = (
                        metrics.cost_by_model.get(model, 0.0) + row[1]
                    )
                except (json.JSONDecodeError, AttributeError):
                    pass

        return metrics

    # ── Cleanup ────────────────────────────────────────────────────────

    async def delete_all(self) -> int:
        """Delete all traces and spans. Returns count of deleted traces."""
        async with self.db.execute("SELECT COUNT(*) FROM traces") as cur:
            row = await cur.fetchone()
            count = row[0] if row else 0
        await self.db.execute("DELETE FROM spans")
        await self.db.execute("DELETE FROM traces")
        await self.db.commit()
        return count

    async def export_all(self) -> dict[str, Any]:
        """Export all traces and spans as a JSON-serializable dict."""
        traces: list[dict[str, Any]] = []
        async with self.db.execute(
            "SELECT * FROM traces ORDER BY started_at DESC"
        ) as cur:
            async for row in cur:
                t = self._row_to_trace(row)
                spans = await self.get_spans_for_trace(t.trace_id)
                traces.append(
                    {
                        "trace": t.model_dump(),
                        "spans": [s.model_dump() for s in spans],
                    }
                )
        return {"version": "1.0", "traces": traces}

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_trace(row: aiosqlite.Row) -> TraceRecord:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return TraceRecord(
            trace_id=row["trace_id"],
            workflow_name=row["workflow_name"],
            group_id=row["group_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            status=TraceStatus(row["status"]),
            metadata=metadata,
            total_tokens=row["total_tokens"],
            total_cost=row["total_cost"],
        )

    @staticmethod
    def _row_to_span(row: aiosqlite.Row) -> SpanRecord:
        span_data = row["span_data"]
        if isinstance(span_data, str):
            span_data = json.loads(span_data)
        error = row["error"]
        if isinstance(error, str):
            error = json.loads(error)
        return SpanRecord(
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            parent_id=row["parent_id"],
            span_type=row["span_type"],
            name=row["name"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            span_data=span_data,
            error=error,
            cost=row["cost"],
        )


# ── Synchronous helper for SDK (non-async context) ────────────────────────


class SyncDatabase:
    """Synchronous SQLite database wrapper for the SDK processor."""

    def __init__(self, db_path: str = "./traceboard.db"):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected.")
        return self._conn

    def insert_trace(self, trace: TraceRecord) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO traces
               (trace_id, workflow_name, group_id, started_at, ended_at,
                status, metadata, total_tokens, total_cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace.trace_id,
                trace.workflow_name,
                trace.group_id,
                trace.started_at,
                trace.ended_at,
                trace.status.value,
                json.dumps(trace.metadata),
                trace.total_tokens,
                trace.total_cost,
            ),
        )
        self.conn.commit()

    def update_trace_end(self, trace_id: str, ended_at: float, status: str, total_tokens: int, total_cost: float) -> None:
        self.conn.execute(
            """UPDATE traces SET ended_at=?, status=?, total_tokens=?, total_cost=?
               WHERE trace_id=?""",
            (ended_at, status, total_tokens, total_cost, trace_id),
        )
        self.conn.commit()

    def insert_span(self, span: SpanRecord) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO spans
               (span_id, trace_id, parent_id, span_type, name,
                started_at, ended_at, span_data, error, cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                span.span_id, span.trace_id, span.parent_id,
                span.span_type.value, span.name, span.started_at,
                span.ended_at, json.dumps(span.span_data),
                json.dumps(span.error) if span.error else None, span.cost,
            ),
        )
        self.conn.commit()

    def update_span_end(self, span_id: str, ended_at: float, span_data: dict, error: dict | None, cost: float) -> None:
        self.conn.execute(
            """UPDATE spans SET ended_at=?, span_data=?, error=?, cost=?
               WHERE span_id=?""",
            (ended_at, json.dumps(span_data), json.dumps(error) if error else None, cost, span_id),
        )
        self.conn.commit()
