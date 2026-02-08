"""Tests for TraceBoardProcessor."""

import os
import tempfile
import time

import pytest

from traceboard.config import TraceboardConfig
from traceboard.sdk.processor import TraceBoardProcessor
from traceboard.server.models import SpanType


class MockTrace:
    """Minimal mock of an OpenAI Agents SDK Trace object."""

    def __init__(self, trace_id="trace_test123", name="Test Workflow", group_id=None):
        self.trace_id = trace_id
        self.name = name
        self.group_id = group_id
        self.metadata = {"test": True}


class MockGenerationSpanData:
    """Mock of GenerationSpanData."""

    def __init__(self):
        self.model = "gpt-4o-mini"
        self.input = [{"role": "user", "content": "Hello"}]
        self.output = "Hi there!"
        self.input_tokens = 10
        self.output_tokens = 5

    # Make the class name match what the processor expects
    pass


# Rename class to match the expected name
MockGenerationSpanData.__name__ = "GenerationSpanData"
MockGenerationSpanData.__qualname__ = "GenerationSpanData"


class MockFunctionSpanData:
    """Mock of FunctionSpanData."""

    def __init__(self):
        self.name = "get_weather"
        self.input = '{"city": "Tokyo"}'
        self.output = "Sunny, 22°C"


MockFunctionSpanData.__name__ = "FunctionSpanData"
MockFunctionSpanData.__qualname__ = "FunctionSpanData"


class MockSpan:
    """Minimal mock of an OpenAI Agents SDK Span object."""

    def __init__(self, span_id, trace_id, parent_id=None, span_data=None, name=None):
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.span_data = span_data
        self.name = name
        self.error = None


class TestTraceBoardProcessor:
    """Test suite for TraceBoardProcessor."""

    def setup_method(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_traces.db")
        self.config = TraceboardConfig(db_path=self.db_path)
        self.processor = TraceBoardProcessor(config=self.config)

    def teardown_method(self):
        """Clean up."""
        self.processor.shutdown()

    def test_trace_lifecycle(self):
        """Test basic trace start and end."""
        trace = MockTrace()

        self.processor.on_trace_start(trace)
        self.processor.on_trace_end(trace)

        # Verify the trace was written (check via sync db)
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace.trace_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["workflow_name"] == "Test Workflow"
        assert row["status"] == "completed"
        assert row["ended_at"] is not None

    def test_span_lifecycle(self):
        """Test span start and end with generation data."""
        trace = MockTrace()
        span_data = MockGenerationSpanData()
        span = MockSpan(
            span_id="span_gen_001",
            trace_id=trace.trace_id,
            span_data=span_data,
            name="LLM Call",
        )

        self.processor.on_trace_start(trace)
        self.processor.on_span_start(span)
        self.processor.on_span_end(span)
        self.processor.on_trace_end(trace)

        # Verify the span was written
        import sqlite3
        import json

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM spans WHERE span_id = ?", (span.span_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["span_type"] == "generation"
        assert row["name"] == "LLM Call"
        assert row["cost"] > 0

        data = json.loads(row["span_data"])
        assert data["model"] == "gpt-4o-mini"

    def test_function_span(self):
        """Test function tool call span."""
        trace = MockTrace()
        span_data = MockFunctionSpanData()
        span = MockSpan(
            span_id="span_fn_001",
            trace_id=trace.trace_id,
            span_data=span_data,
        )

        self.processor.on_trace_start(trace)
        self.processor.on_span_start(span)
        self.processor.on_span_end(span)
        self.processor.on_trace_end(trace)

        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM spans WHERE span_id = ?", (span.span_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["span_type"] == "function"

    def test_cost_aggregation(self):
        """Test that costs are summed up to the trace level."""
        trace = MockTrace()

        # Two generation spans
        span_data1 = MockGenerationSpanData()
        span1 = MockSpan("span_1", trace.trace_id, span_data=span_data1)

        span_data2 = MockGenerationSpanData()
        span_data2.input_tokens = 20
        span_data2.output_tokens = 10
        span2 = MockSpan("span_2", trace.trace_id, span_data=span_data2)

        self.processor.on_trace_start(trace)
        self.processor.on_span_start(span1)
        self.processor.on_span_end(span1)
        self.processor.on_span_start(span2)
        self.processor.on_span_end(span2)
        self.processor.on_trace_end(trace)

        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace.trace_id,)
        ).fetchone()
        conn.close()

        assert row["total_tokens"] > 0
        assert row["total_cost"] > 0

    def test_force_flush_noop(self):
        """Test that force_flush doesn't raise."""
        self.processor.force_flush()
