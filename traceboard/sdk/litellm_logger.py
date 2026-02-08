"""LiteLLM adapter for TraceBoard.

Provides a ``CustomLogger`` subclass that captures every LLM call made
through LiteLLM, regardless of the underlying provider.

Usage::

    import traceboard
    traceboard.init()  # auto-detects litellm if installed

    # Or manually:
    from traceboard.sdk.litellm_logger import TraceBoardLiteLLMLogger
    import litellm
    litellm.callbacks = [TraceBoardLiteLLMLogger()]
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from traceboard.config import TraceboardConfig
from traceboard.sdk._base import BaseTracer

logger = logging.getLogger("traceboard")


class TraceBoardLiteLLMLogger(BaseTracer):
    """LiteLLM custom logger that writes traces to TraceBoard.

    Inherits from both :class:`BaseTracer` and LiteLLM's
    ``CustomLogger``.  Registration is handled automatically by
    ``traceboard.init()`` or manually via
    ``litellm.callbacks = [TraceBoardLiteLLMLogger()]``.
    """

    def __init__(self, config: TraceboardConfig | None = None):
        super().__init__(config)
        self._pending: dict[str, dict[str, Any]] = {}

        # Dynamically inherit from LiteLLM's CustomLogger so that
        # litellm recognises this object.
        try:
            from litellm.integrations.custom_logger import CustomLogger

            self.__class__ = type(
                "TraceBoardLiteLLMLogger",
                (TraceBoardLiteLLMLogger.__bases__[0], CustomLogger),
                dict(TraceBoardLiteLLMLogger.__dict__),
            )
        except ImportError:
            logger.debug("litellm not installed; logger works standalone")

    # ── Sync callbacks ────────────────────────────────────────────────

    def log_pre_api_call(
        self, model: str, messages: list[Any], kwargs: dict[str, Any]
    ) -> None:
        """Called before an API call is made."""
        try:
            call_id = kwargs.get("litellm_call_id", "") or self._generate_id("call")
            trace_id, span_id = self.record_llm_start(
                workflow_name=f"LiteLLM: {model}",
                model=model,
                metadata={
                    "provider": "litellm",
                    "litellm_call_id": str(call_id),
                },
            )
            self._pending[str(call_id)] = {
                "trace_id": trace_id,
                "span_id": span_id,
                "model": model,
            }
        except Exception:
            logger.debug("TraceBoard: failed in log_pre_api_call")

    def log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Called on successful API call."""
        self._handle_success(kwargs, response_obj, start_time, end_time)

    def log_failure_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Called on failed API call."""
        self._handle_failure(kwargs, start_time, end_time)

    def log_post_api_call(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Called after API call completes (before success/failure)."""
        pass

    # ── Async callbacks ───────────────────────────────────────────────

    async def async_log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Async version of log_success_event."""
        self._handle_success(kwargs, response_obj, start_time, end_time)

    async def async_log_failure_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Async version of log_failure_event."""
        self._handle_failure(kwargs, start_time, end_time)

    # ── Shared logic ──────────────────────────────────────────────────

    def _resolve_ctx(self, kwargs: dict[str, Any]) -> dict[str, Any] | None:
        """Find the pending context for this call."""
        call_id = str(kwargs.get("litellm_call_id", ""))
        ctx = self._pending.pop(call_id, None)
        if ctx:
            return ctx

        # Fallback: create trace on-the-fly if pre_api_call was missed
        model = kwargs.get("model", "unknown")
        trace_id, span_id = self.record_llm_start(
            workflow_name=f"LiteLLM: {model}",
            model=model,
            metadata={"provider": "litellm"},
        )
        return {"trace_id": trace_id, "span_id": span_id, "model": model}

    def _handle_success(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Shared handler for successful calls."""
        try:
            ctx = self._resolve_ctx(kwargs)
            if ctx is None:
                return

            # Extract token info
            logging_obj = kwargs.get("standard_logging_object", {})
            input_tokens = logging_obj.get("prompt_tokens", 0) or 0
            output_tokens = logging_obj.get("completion_tokens", 0) or 0

            # Fallback: try response_obj.usage
            if not input_tokens and hasattr(response_obj, "usage"):
                usage = response_obj.usage
                if usage:
                    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    output_tokens = getattr(usage, "completion_tokens", 0) or 0

            model = getattr(response_obj, "model", None) or ctx["model"]

            # Extract response text
            response_text = ""
            choices = getattr(response_obj, "choices", [])
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg:
                    response_text = getattr(msg, "content", "") or ""

            self.record_llm_end(
                trace_id=ctx["trace_id"],
                span_id=ctx["span_id"],
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                response_text=response_text,
            )
        except Exception:
            logger.debug("TraceBoard: error in litellm success handler")

    def _handle_failure(
        self,
        kwargs: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Shared handler for failed calls."""
        try:
            ctx = self._resolve_ctx(kwargs)
            if ctx is None:
                return

            exception = kwargs.get("exception", "Unknown error")
            error_info = {
                "type": type(exception).__name__ if isinstance(exception, Exception) else "Error",
                "message": str(exception),
            }

            self.record_llm_end(
                trace_id=ctx["trace_id"],
                span_id=ctx["span_id"],
                model=ctx["model"],
                error=error_info,
            )
        except Exception:
            logger.debug("TraceBoard: error in litellm failure handler")
