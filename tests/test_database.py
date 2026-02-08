"""Tests for the async Database class."""

import os
import tempfile

import pytest
import pytest_asyncio

from traceboard.server.database import Database
from traceboard.server.models import SpanRecord, SpanType, TraceRecord, TraceStatus


@pytest_asyncio.fixture
async def db():
    """Create a temporary database for testing."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    database = Database(db_path=db_path)
    await database.connect()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_insert_and_get_trace(db: Database):
    """Test inserting and retrieving a trace."""
    trace = TraceRecord(
        trace_id="trace_abc123",
        workflow_name="Test Flow",
        started_at=1000.0,
        ended_at=1005.0,
        status=TraceStatus.COMPLETED,
        total_tokens=100,
        total_cost=0.001,
    )
    await db.insert_trace(trace)
    result = await db.get_trace("trace_abc123")

    assert result is not None
    assert result.trace_id == "trace_abc123"
    assert result.workflow_name == "Test Flow"
    assert result.status == TraceStatus.COMPLETED
    assert result.total_tokens == 100


@pytest.mark.asyncio
async def test_list_traces_pagination(db: Database):
    """Test trace listing with pagination."""
    for i in range(10):
        trace = TraceRecord(
            trace_id=f"trace_{i:03d}",
            workflow_name=f"Flow {i}",
            started_at=1000.0 + i,
            status=TraceStatus.COMPLETED,
        )
        await db.insert_trace(trace)

    items, total = await db.list_traces(page=1, page_size=3)
    assert total == 10
    assert len(items) == 3

    items2, _ = await db.list_traces(page=2, page_size=3)
    assert len(items2) == 3


@pytest.mark.asyncio
async def test_list_traces_filter_status(db: Database):
    """Test filtering traces by status."""
    await db.insert_trace(
        TraceRecord(trace_id="t1", started_at=1000, status=TraceStatus.COMPLETED)
    )
    await db.insert_trace(
        TraceRecord(trace_id="t2", started_at=1001, status=TraceStatus.ERROR)
    )

    items, total = await db.list_traces(status="error")
    assert total == 1
    assert items[0].trace_id == "t2"


@pytest.mark.asyncio
async def test_span_operations(db: Database):
    """Test span insert and retrieval."""
    trace = TraceRecord(trace_id="trace_spans", started_at=1000.0)
    await db.insert_trace(trace)

    span = SpanRecord(
        span_id="span_001",
        trace_id="trace_spans",
        span_type=SpanType.GENERATION,
        name="LLM Call",
        started_at=1000.5,
        ended_at=1002.0,
        span_data={"model": "gpt-4o", "input_tokens": 50, "output_tokens": 20},
        cost=0.0003,
    )
    await db.insert_span(span)

    spans = await db.get_spans_for_trace("trace_spans")
    assert len(spans) == 1
    assert spans[0].span_id == "span_001"
    assert spans[0].span_data["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_build_span_tree(db: Database):
    """Test building a nested span tree."""
    trace = TraceRecord(trace_id="trace_tree", started_at=1000.0)
    await db.insert_trace(trace)

    # Root span
    await db.insert_span(
        SpanRecord(
            span_id="root",
            trace_id="trace_tree",
            span_type=SpanType.AGENT,
            name="Agent",
            started_at=1000.0,
            ended_at=1005.0,
        )
    )
    # Child span
    await db.insert_span(
        SpanRecord(
            span_id="child1",
            trace_id="trace_tree",
            parent_id="root",
            span_type=SpanType.GENERATION,
            name="LLM",
            started_at=1001.0,
            ended_at=1003.0,
        )
    )
    # Grandchild
    await db.insert_span(
        SpanRecord(
            span_id="grandchild1",
            trace_id="trace_tree",
            parent_id="child1",
            span_type=SpanType.FUNCTION,
            name="Tool",
            started_at=1002.0,
            ended_at=1002.5,
        )
    )

    tree = await db.build_span_tree("trace_tree")
    assert len(tree) == 1  # One root
    assert tree[0].span_id == "root"
    assert len(tree[0].children) == 1
    assert tree[0].children[0].span_id == "child1"
    assert len(tree[0].children[0].children) == 1
    assert tree[0].children[0].children[0].span_id == "grandchild1"


@pytest.mark.asyncio
async def test_metrics(db: Database):
    """Test aggregated metrics."""
    await db.insert_trace(
        TraceRecord(
            trace_id="t1",
            started_at=1000.0,
            ended_at=1005.0,
            status=TraceStatus.COMPLETED,
            total_tokens=100,
            total_cost=0.01,
        )
    )
    await db.insert_trace(
        TraceRecord(
            trace_id="t2",
            started_at=1010.0,
            ended_at=1020.0,
            status=TraceStatus.COMPLETED,
            total_tokens=200,
            total_cost=0.02,
        )
    )

    metrics = await db.get_metrics()
    assert metrics.total_traces == 2
    assert metrics.total_tokens == 300
    assert abs(metrics.total_cost - 0.03) < 0.0001
    assert metrics.traces_by_status.get("completed") == 2


@pytest.mark.asyncio
async def test_delete_all(db: Database):
    """Test deleting all data."""
    await db.insert_trace(TraceRecord(trace_id="t1", started_at=1000.0))
    await db.insert_trace(TraceRecord(trace_id="t2", started_at=1001.0))

    count = await db.delete_all()
    assert count == 2

    items, total = await db.list_traces()
    assert total == 0


@pytest.mark.asyncio
async def test_export_all(db: Database):
    """Test exporting all data."""
    await db.insert_trace(
        TraceRecord(trace_id="t1", started_at=1000.0, workflow_name="Test")
    )
    await db.insert_span(
        SpanRecord(
            span_id="s1",
            trace_id="t1",
            span_type=SpanType.AGENT,
            started_at=1000.0,
        )
    )

    data = await db.export_all()
    assert data["version"] == "1.0"
    assert len(data["traces"]) == 1
    assert len(data["traces"][0]["spans"]) == 1
