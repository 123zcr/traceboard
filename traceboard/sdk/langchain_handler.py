"""LangChain adapter for TraceBoard.

Provides a ``BaseCallbackHandler`` subclass that captures LLM calls,
tool invocations, and chain executions from any LangChain workflow.

Usage::

    import traceboard
    traceboard.init()  # auto-detects langchain if installed

    # Or manually:
    from traceboard.sdk.langchain_handler import TraceBoardCallbackHandler
    handler = TraceBoardCallbackHandler()
    llm = ChatOpenAI(callbacks=[handler])
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from traceboard.config import TraceboardConfig
from traceboard.sdk._base import BaseTracer

logger = logging.getLogger("traceboard")


class TraceBoardCallbackHandler(BaseTracer):
    """LangChain callback handler that writes traces to TraceBoard.

    Implements ``BaseCallbackHandler`` from ``langchain_core``.
    Pass an instance to LangChain via the ``callbacks`` parameter.
    """

    # We lazily inherit from BaseCallbackHandler to avoid hard-importing
    # langchain_core at module level (it's an optional dependency).

    def __init__(self, config: TraceboardConfig | None = None):
        super().__init__(config)
        self._runs: dict[UUID, dict[str, Any]] = {}

        # Dynamically inherit from BaseCallbackHandler so LangChain
        # recognises this object as a valid handler.
        try:
            from langchain_core.callbacks import BaseCallbackHandler

            # Mixin at instance level — makes isinstance() checks pass.
            self.__class__ = type(
                "TraceBoardCallbackHandler",
                (TraceBoardCallbackHandler.__bases__[0], BaseCallbackHandler),
                dict(TraceBoardCallbackHandler.__dict__),
            )
        except ImportError:
            logger.debug(
                "langchain_core not installed; handler works standalone"
            )

    # ── LLM callbacks ─────────────────────────────────────────────────

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when an LLM starts generating."""
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "langchain-llm")
        )
        trace_id, span_id = self.record_llm_start(
            workflow_name=f"LangChain: {model}",
            model=model,
            metadata={
                "provider": "langchain",
                "tags": tags or [],
                **(metadata or {}),
            },
        )
        self._runs[run_id] = {
            "trace_id": trace_id,
            "span_id": span_id,
            "model": model,
            "started_at": time.time(),
        }

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chat model starts (ChatOpenAI, ChatAnthropic, etc.)."""
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "langchain-chat")
        )
        trace_id, span_id = self.record_llm_start(
            workflow_name=f"LangChain: {model}",
            model=model,
            metadata={
                "provider": "langchain",
                "tags": tags or [],
                **(metadata or {}),
            },
        )
        self._runs[run_id] = {
            "trace_id": trace_id,
            "span_id": span_id,
            "model": model,
            "started_at": time.time(),
        }

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM finishes generating."""
        ctx = self._runs.pop(run_id, None)
        if ctx is None:
            return

        # Extract token usage
        input_tokens = 0
        output_tokens = 0
        model = ctx["model"]

        llm_output = getattr(response, "llm_output", None) or {}
        token_usage = llm_output.get("token_usage", {})
        if token_usage:
            input_tokens = token_usage.get("prompt_tokens", 0) or 0
            output_tokens = token_usage.get("completion_tokens", 0) or 0

        # Also check response-level usage (newer LangChain versions)
        if not input_tokens and hasattr(response, "usage_metadata"):
            usage_meta = response.usage_metadata or {}
            input_tokens = usage_meta.get("input_tokens", 0) or 0
            output_tokens = usage_meta.get("output_tokens", 0) or 0

        # Extract model name from output if available
        if llm_output.get("model_name"):
            model = llm_output["model_name"]

        # Extract response text
        response_text = ""
        generations = getattr(response, "generations", [])
        if generations:
            for gen_list in generations:
                for gen in gen_list:
                    text = getattr(gen, "text", "") or ""
                    if text:
                        response_text += text

        self.record_llm_end(
            trace_id=ctx["trace_id"],
            span_id=ctx["span_id"],
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_text=response_text,
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM call errors."""
        ctx = self._runs.pop(run_id, None)
        if ctx is None:
            return

        self.record_llm_end(
            trace_id=ctx["trace_id"],
            span_id=ctx["span_id"],
            model=ctx["model"],
            error={"type": type(error).__name__, "message": str(error)},
        )

    # ── Tool callbacks ────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts running."""
        tool_name = serialized.get("name", "tool")
        self._runs[run_id] = {
            "tool_name": tool_name,
            "tool_input": input_str,
            "started_at": time.time(),
            "parent_run_id": parent_run_id,
        }

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes."""
        ctx = self._runs.pop(run_id, None)
        if ctx is None or "tool_name" not in ctx:
            return

        # Find parent trace_id
        parent_ctx = self._runs.get(parent_run_id) if parent_run_id else None
        trace_id = (parent_ctx or {}).get("trace_id")
        if not trace_id:
            return

        self.record_tool_call(
            trace_id=trace_id,
            tool_name=ctx["tool_name"],
            tool_input=str(ctx.get("tool_input", "")),
            tool_output=str(output)[:2000],
            parent_span_id=(parent_ctx or {}).get("span_id"),
            started_at=ctx.get("started_at"),
            ended_at=time.time(),
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool errors."""
        self._runs.pop(run_id, None)

    # ── Chain callbacks (lightweight tracking) ────────────────────────

    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], **kwargs: Any
    ) -> None:
        pass

    def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        pass

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        pass
