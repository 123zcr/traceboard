"""Tests for TraceExporter (JSON and CSV export)."""

import json
import os
import tempfile

import pytest
import pytest_asyncio

from traceboard.sdk.exporter import TraceExporter
from traceboard.server.database import Database
from traceboard.server.models import SpanRecord, SpanType, TraceRecord, TraceStatus


@pytest_asyncio.fixture
async def populated_db():
    """Create a temporary database with sample data."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_export.db")

    db = Database(db_path=db_path)
    await db.connect()

    # Insert test traces
    await db.insert_trace(
        TraceRecord(
            trace_id="trace_001",
            workflow_name="Weather Agent",
            started_at=1000.0,
            ended_at=1005.0,
            status=TraceStatus.COMPLETED,
            total_tokens=150,
            total_cost=0.001,
        )
    )
    await db.insert_trace(
        TraceRecord(
            trace_id="trace_002",
            workflow_name="Math Agent",
            started_at=1010.0,
            ended_at=1018.0,
            status=TraceStatus.COMPLETED,
            total_tokens=200,
            total_cost=0.002,
        )
    )

    # Insert test spans
    await db.insert_span(
        SpanRecord(
            span_id="span_001",
            trace_id="trace_001",
            span_type=SpanType.AGENT,
            name="Weather Agent",
            started_at=1000.0,
            ended_at=1005.0,
        )
    )
    await db.insert_span(
        SpanRecord(
            span_id="span_002",
            trace_id="trace_001",
            parent_id="span_001",
            span_type=SpanType.GENERATION,
            name="LLM Call",
            started_at=1001.0,
            ended_at=1003.0,
            span_data={"model": "gpt-4o-mini", "input_tokens": 50, "output_tokens": 20},
            cost=0.0003,
        )
    )
    await db.insert_span(
        SpanRecord(
            span_id="span_003",
            trace_id="trace_001",
            parent_id="span_001",
            span_type=SpanType.FUNCTION,
            name="get_weather",
            started_at=1003.0,
            ended_at=1004.0,
            span_data={"name": "get_weather", "input": '{"city": "Tokyo"}', "output": "Sunny"},
        )
    )

    await db.close()
    yield db_path


@pytest.mark.asyncio
async def test_export_json_to_memory(populated_db):
    """Test in-memory JSON export."""
    exporter = TraceExporter(populated_db)
    data = exporter.export_json()

    assert data["version"] == "1.0"
    assert "exported_at" in data
    assert data["trace_count"] == 2
    assert len(data["traces"]) == 2

    # Verify trace structure
    trace = data["traces"][0]  # Most recent first
    assert "trace" in trace
    assert "spans" in trace


@pytest.mark.asyncio
async def test_export_json_to_file(populated_db):
    """Test JSON export to file."""
    tmpdir = tempfile.mkdtemp()
    output = os.path.join(tmpdir, "export.json")

    exporter = TraceExporter(populated_db)
    data = exporter.export_json(output, pretty=True)

    assert os.path.exists(output)
    with open(output, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["trace_count"] == 2


@pytest.mark.asyncio
async def test_export_json_filtered(populated_db):
    """Test JSON export with trace ID filter."""
    exporter = TraceExporter(populated_db)
    data = exporter.export_json(trace_ids=["trace_001"])

    assert data["trace_count"] == 1
    assert data["traces"][0]["trace"]["trace_id"] == "trace_001"
    assert len(data["traces"][0]["spans"]) == 3


@pytest.mark.asyncio
async def test_export_csv_to_memory(populated_db):
    """Test in-memory CSV export."""
    exporter = TraceExporter(populated_db)
    csv_content = exporter.export_csv()

    lines = csv_content.strip().split("\n")
    assert len(lines) == 3  # header + 2 traces

    header = lines[0]
    assert "trace_id" in header
    assert "workflow_name" in header
    assert "total_cost" in header


@pytest.mark.asyncio
async def test_export_csv_to_file(populated_db):
    """Test CSV export to file with spans."""
    tmpdir = tempfile.mkdtemp()
    output = os.path.join(tmpdir, "traces.csv")

    exporter = TraceExporter(populated_db)
    exporter.export_csv(output, include_spans=True)

    assert os.path.exists(output)
    spans_path = os.path.join(tmpdir, "traces_spans.csv")
    assert os.path.exists(spans_path)

    # Verify spans CSV
    with open(spans_path, encoding="utf-8") as f:
        lines = f.read().strip().split("\n")
    assert len(lines) >= 4  # header + 3 spans


@pytest.mark.asyncio
async def test_export_csv_without_spans(populated_db):
    """Test CSV export without spans file."""
    tmpdir = tempfile.mkdtemp()
    output = os.path.join(tmpdir, "traces_only.csv")

    exporter = TraceExporter(populated_db)
    exporter.export_csv(output, include_spans=False)

    assert os.path.exists(output)
    spans_path = os.path.join(tmpdir, "traces_only_spans.csv")
    assert not os.path.exists(spans_path)


@pytest.mark.asyncio
async def test_export_nonexistent_db():
    """Test export from non-existent database."""
    exporter = TraceExporter("/nonexistent/path/db.sqlite")
    with pytest.raises(FileNotFoundError):
        exporter.export_json()
