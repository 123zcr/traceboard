"""TraceBoard exporters.

Provides utilities for exporting trace data to JSON and CSV formats.
Supports both file-based and in-memory export for local data analysis
and sharing.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceExporter:
    """Export traced data from the local SQLite database.

    Supports exporting to JSON and CSV formats, either to files
    or as in-memory strings/dicts.

    Usage::

        exporter = TraceExporter("./traceboard.db")

        # Export all traces to JSON
        exporter.export_json("traces.json")

        # Export specific traces to CSV
        exporter.export_csv("traces.csv", trace_ids=["trace_abc123"])

        # Get data in memory (no file)
        data = exporter.export_json()
    """

    def __init__(self, db_path: str = "./traceboard.db"):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Open a read-only connection to the database."""
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── JSON Export ────────────────────────────────────────────────────

    def export_json(
        self,
        output_path: str | None = None,
        *,
        pretty: bool = True,
        trace_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Export traces and spans as JSON.

        Args:
            output_path: If provided, write JSON to this file path.
            pretty: Whether to pretty-print the JSON output.
            trace_ids: Optional list of trace IDs to export.
                If None, exports all traces.

        Returns:
            The exported data as a dictionary.
        """
        conn = self._connect()
        try:
            data = self._build_export_data(conn, trace_ids)
        finally:
            conn.close()

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            indent = 2 if pretty else None
            path.write_text(
                json.dumps(data, indent=indent, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

        return data

    # ── CSV Export ─────────────────────────────────────────────────────

    def export_csv(
        self,
        output_path: str | None = None,
        *,
        trace_ids: list[str] | None = None,
        include_spans: bool = True,
    ) -> str:
        """Export traces (and optionally spans) as CSV.

        When ``include_spans`` is True (default) and ``output_path`` is given,
        two files are created:

        - ``{output_path}`` — traces table
        - ``{stem}_spans.csv`` — spans table

        Args:
            output_path: If provided, write CSV to this file path.
            trace_ids: Optional list of trace IDs to export.
            include_spans: Whether to also export spans (default True).

        Returns:
            The traces CSV content as a string.
        """
        conn = self._connect()
        try:
            traces_csv = self._traces_to_csv(conn, trace_ids)
            spans_csv = ""
            if include_spans:
                spans_csv = self._spans_to_csv(conn, trace_ids)
        finally:
            conn.close()

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(traces_csv, encoding="utf-8")

            if include_spans and spans_csv:
                spans_path = path.with_name(f"{path.stem}_spans{path.suffix}")
                spans_path.write_text(spans_csv, encoding="utf-8")

        return traces_csv

    # ── Internal helpers ──────────────────────────────────────────────

    def _build_export_data(
        self,
        conn: sqlite3.Connection,
        trace_ids: list[str] | None,
    ) -> dict[str, Any]:
        """Build the full JSON export data structure."""
        where, params = self._build_where(trace_ids)

        traces: list[dict[str, Any]] = []
        for row in conn.execute(
            f"SELECT * FROM traces {where} ORDER BY started_at DESC",
            params,
        ):
            trace_data = dict(row)
            trace_data["metadata"] = json.loads(trace_data.get("metadata") or "{}")

            # Attach spans
            spans: list[dict[str, Any]] = []
            for span_row in conn.execute(
                "SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at ASC",
                (trace_data["trace_id"],),
            ):
                span = dict(span_row)
                span["span_data"] = json.loads(span.get("span_data") or "{}")
                if span.get("error"):
                    span["error"] = json.loads(span["error"])
                spans.append(span)

            traces.append({"trace": trace_data, "spans": spans})

        return {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "trace_count": len(traces),
            "traces": traces,
        }

    def _traces_to_csv(
        self,
        conn: sqlite3.Connection,
        trace_ids: list[str] | None,
    ) -> str:
        """Convert traces to CSV format."""
        where, params = self._build_where(trace_ids)
        buf = io.StringIO()
        writer = csv.writer(buf)

        writer.writerow([
            "trace_id",
            "workflow_name",
            "group_id",
            "started_at",
            "ended_at",
            "status",
            "total_tokens",
            "total_cost",
            "duration_s",
        ])

        for row in conn.execute(
            f"SELECT * FROM traces {where} ORDER BY started_at DESC",
            params,
        ):
            started = row["started_at"]
            ended = row["ended_at"]
            duration = round(ended - started, 3) if ended else None
            writer.writerow([
                row["trace_id"],
                row["workflow_name"],
                row["group_id"] or "",
                started,
                ended or "",
                row["status"],
                row["total_tokens"],
                row["total_cost"],
                duration if duration is not None else "",
            ])

        return buf.getvalue()

    def _spans_to_csv(
        self,
        conn: sqlite3.Connection,
        trace_ids: list[str] | None,
    ) -> str:
        """Convert spans to CSV format."""
        where, params = self._build_where(trace_ids)
        buf = io.StringIO()
        writer = csv.writer(buf)

        writer.writerow([
            "span_id",
            "trace_id",
            "parent_id",
            "span_type",
            "name",
            "started_at",
            "ended_at",
            "cost",
            "duration_s",
            "model",
            "input_tokens",
            "output_tokens",
            "error",
        ])

        for row in conn.execute(
            f"SELECT * FROM spans {where} ORDER BY started_at ASC",
            params,
        ):
            span_data = json.loads(row["span_data"] or "{}")
            started = row["started_at"]
            ended = row["ended_at"]
            duration = round(ended - started, 3) if ended else None
            error = row["error"]
            error_str = ""
            if error:
                try:
                    error_str = json.dumps(json.loads(error))
                except (json.JSONDecodeError, TypeError):
                    error_str = str(error)

            writer.writerow([
                row["span_id"],
                row["trace_id"],
                row["parent_id"] or "",
                row["span_type"],
                row["name"],
                started,
                ended or "",
                row["cost"],
                duration if duration is not None else "",
                span_data.get("model", ""),
                span_data.get("input_tokens", ""),
                span_data.get("output_tokens", ""),
                error_str,
            ])

        return buf.getvalue()

    @staticmethod
    def _build_where(
        trace_ids: list[str] | None,
    ) -> tuple[str, list[str]]:
        """Build a WHERE clause for optional trace ID filtering."""
        if not trace_ids:
            return "", []
        placeholders = ",".join("?" for _ in trace_ids)
        return f"WHERE trace_id IN ({placeholders})", list(trace_ids)
