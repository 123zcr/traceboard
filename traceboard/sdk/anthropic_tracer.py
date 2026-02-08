"""Anthropic SDK adapter for TraceBoard.

Instruments the Anthropic Python SDK by injecting httpx event hooks
that capture request/response data for every API call.

Usage::

    import traceboard
    traceboard.init()  # auto-detects anthropic if installed

    # Or manually:
    from traceboard.sdk.anthropic_tracer import AnthropicTracer
    tracer = AnthropicTracer()
    client = tracer.instrument()
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from traceboard.config import TraceboardConfig
from traceboard.sdk._base import BaseTracer

logger = logging.getLogger("traceboard")


class AnthropicTracer(BaseTracer):
    """Traces Anthropic SDK calls via httpx event hooks."""

    def __init__(self, config: TraceboardConfig | None = None):
        super().__init__(config)
        self._pending: dict[int, dict[str, Any]] = {}

    def instrument(self, client: Any | None = None) -> Any:
        """Instrument an Anthropic client, or create a new instrumented one.

        Args:
            client: An existing ``anthropic.Anthropic`` or
                ``anthropic.AsyncAnthropic`` instance.  If *None*, a new
                ``Anthropic()`` client is created.

        Returns:
            The instrumented client.
        """
        try:
            import anthropic
            import httpx
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for Anthropic tracing. "
                "Install it with: pip install traceboard[anthropic]"
            )

        if client is not None:
            # Patch an existing client's httpx client
            self._patch_httpx_client(client)
            return client

        # Create a new instrumented client
        http_client = httpx.Client(
            event_hooks={
                "request": [self._on_request],
                "response": [self._on_response],
            }
        )
        return anthropic.Anthropic(http_client=http_client)

    def instrument_async(self, client: Any | None = None) -> Any:
        """Instrument an async Anthropic client."""
        try:
            import anthropic
            import httpx
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required. "
                "Install with: pip install traceboard[anthropic]"
            )

        if client is not None:
            self._patch_httpx_client(client)
            return client

        http_client = httpx.AsyncClient(
            event_hooks={
                "request": [self._on_async_request],
                "response": [self._on_async_response],
            }
        )
        return anthropic.AsyncAnthropic(http_client=http_client)

    # ── httpx sync hooks ──────────────────────────────────────────────

    def _on_request(self, request: Any) -> None:
        """Sync hook: called before request is sent."""
        if "/messages" not in str(request.url):
            return
        try:
            body = json.loads(request.content) if request.content else {}
            model = body.get("model", "claude")
            trace_id, span_id = self.record_llm_start(
                workflow_name=f"Anthropic: {model}",
                model=model,
                metadata={"provider": "anthropic", "sdk": "anthropic-python"},
            )
            self._pending[id(request)] = {
                "trace_id": trace_id,
                "span_id": span_id,
                "model": model,
                "started_at": time.time(),
            }
        except Exception:
            logger.debug("TraceBoard: failed to intercept Anthropic request")

    def _on_response(self, response: Any) -> None:
        """Sync hook: called after response is received."""
        ctx = self._pending.pop(id(response.request), None)
        if ctx is None:
            return
        try:
            response.read()
            data = json.loads(response.content)
            self._finish(ctx, data)
        except Exception:
            logger.debug("TraceBoard: failed to parse Anthropic response")

    # ── httpx async hooks ─────────────────────────────────────────────

    async def _on_async_request(self, request: Any) -> None:
        if "/messages" not in str(request.url):
            return
        try:
            body = json.loads(request.content) if request.content else {}
            model = body.get("model", "claude")
            trace_id, span_id = self.record_llm_start(
                workflow_name=f"Anthropic: {model}",
                model=model,
                metadata={"provider": "anthropic", "sdk": "anthropic-python"},
            )
            self._pending[id(request)] = {
                "trace_id": trace_id,
                "span_id": span_id,
                "model": model,
                "started_at": time.time(),
            }
        except Exception:
            logger.debug("TraceBoard: failed to intercept async Anthropic request")

    async def _on_async_response(self, response: Any) -> None:
        ctx = self._pending.pop(id(response.request), None)
        if ctx is None:
            return
        try:
            await response.aread()
            data = json.loads(response.content)
            self._finish(ctx, data)
        except Exception:
            logger.debug("TraceBoard: failed to parse async Anthropic response")

    # ── Shared finish logic ───────────────────────────────────────────

    def _finish(self, ctx: dict[str, Any], data: dict[str, Any]) -> None:
        """Extract usage from response and record LLM end."""
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        model = data.get("model", ctx.get("model", "claude"))

        # Extract response text
        response_text = ""
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                response_text += block.get("text", "")

        error_info = None
        if data.get("type") == "error":
            error_info = {
                "type": data.get("error", {}).get("type", "api_error"),
                "message": data.get("error", {}).get("message", "Unknown error"),
            }

        self.record_llm_end(
            trace_id=ctx["trace_id"],
            span_id=ctx["span_id"],
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_text=response_text,
            error=error_info,
        )

    # ── Patching existing clients ─────────────────────────────────────

    def _patch_httpx_client(self, anthropic_client: Any) -> None:
        """Add event hooks to an existing Anthropic client's httpx client."""
        http = getattr(anthropic_client, "_client", None)
        if http is None:
            http = getattr(anthropic_client, "http_client", None)
        if http is None:
            logger.warning(
                "TraceBoard: could not find httpx client on Anthropic instance"
            )
            return

        hooks = getattr(http, "event_hooks", None)
        if hooks is None:
            logger.warning("TraceBoard: httpx client has no event_hooks")
            return

        # Detect sync vs async
        import httpx as _httpx

        if isinstance(http, _httpx.AsyncClient):
            hooks.setdefault("request", []).append(self._on_async_request)
            hooks.setdefault("response", []).append(self._on_async_response)
        else:
            hooks.setdefault("request", []).append(self._on_request)
            hooks.setdefault("response", []).append(self._on_response)

        logger.info("TraceBoard: Anthropic client instrumented")
