"""Tests for FastAPI API routes."""

import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from traceboard.server.app import create_app
from traceboard.server.database import Database
from traceboard.server.models import SpanRecord, SpanType, TraceRecord, TraceStatus


@pytest_asyncio.fixture
async def client():
    """Create a test client with a temporary database."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_api.db")
    app = create_app(db_path=db_path)

    # Manually init DB for tests
    db = Database(db_path=db_path)
    await db.connect()
    app.state.db = db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await db.close()


@pytest.mark.asyncio
async def test_list_traces_empty(client: AsyncClient):
    """Test listing traces when database is empty."""
    resp = await client.get("/api/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert data["traces"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_trace_crud(client: AsyncClient):
    """Test creating and retrieving a trace."""
    # Insert directly via DB
    db = client._transport.app.state.db
    await db.insert_trace(
        TraceRecord(
            trace_id="trace_api_test",
            workflow_name="API Test",
            started_at=1000.0,
            ended_at=1005.0,
            status=TraceStatus.COMPLETED,
            total_tokens=50,
            total_cost=0.005,
        )
    )
    await db.insert_span(
        SpanRecord(
            span_id="span_api_1",
            trace_id="trace_api_test",
            span_type=SpanType.AGENT,
            name="Agent",
            started_at=1000.0,
            ended_at=1005.0,
        )
    )

    # List
    resp = await client.get("/api/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["traces"][0]["trace_id"] == "trace_api_test"

    # Detail
    resp = await client.get("/api/traces/trace_api_test")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["trace"]["trace_id"] == "trace_api_test"
    assert len(detail["spans"]) == 1

    # Tree
    resp = await client.get("/api/traces/trace_api_test/tree")
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1


@pytest.mark.asyncio
async def test_get_nonexistent_trace(client: AsyncClient):
    """Test 404 for nonexistent trace."""
    resp = await client.get("/api/traces/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    """Test the metrics endpoint."""
    resp = await client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_traces" in data
    assert "total_cost" in data


@pytest.mark.asyncio
async def test_delete_all(client: AsyncClient):
    """Test deleting all traces."""
    db = client._transport.app.state.db
    await db.insert_trace(TraceRecord(trace_id="t1", started_at=1000.0))

    resp = await client.delete("/api/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 1
