"""Model pricing and cost calculation for TraceBoard.

Prices are in USD per 1M tokens (Standard tier) as of February 2026.
Source: https://platform.openai.com/docs/pricing
"""

from __future__ import annotations

# ── Pricing table ──────────────────────────────────────────────────────────
# Format: model_name -> (input_price_per_1M, output_price_per_1M)

MODEL_PRICES: dict[str, tuple[float, float]] = {
    # ── GPT-5.2 ────────────────────────────────────────────────────────
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.2-chat-latest": (1.75, 14.00),
    "gpt-5.2-codex": (1.75, 14.00),
    "gpt-5.2-pro": (21.00, 168.00),

    # ── GPT-5.1 ────────────────────────────────────────────────────────
    "gpt-5.1": (1.25, 10.00),
    "gpt-5.1-chat-latest": (1.25, 10.00),
    "gpt-5.1-codex": (1.25, 10.00),
    "gpt-5.1-codex-max": (1.25, 10.00),
    "gpt-5.1-codex-mini": (0.25, 2.00),

    # ── GPT-5 ──────────────────────────────────────────────────────────
    "gpt-5": (1.25, 10.00),
    "gpt-5-chat-latest": (1.25, 10.00),
    "gpt-5-codex": (1.25, 10.00),
    "gpt-5-pro": (15.00, 120.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-search-api": (1.25, 10.00),

    # ── GPT-4.1 ────────────────────────────────────────────────────────
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-2025-04-14": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-mini-2025-04-14": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-nano-2025-04-14": (0.10, 0.40),

    # ── GPT-4o ─────────────────────────────────────────────────────────
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-11-20": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4o-2024-05-13": (5.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "chatgpt-4o-latest": (5.00, 15.00),

    # ── o-series reasoning models ──────────────────────────────────────
    "o1": (15.00, 60.00),
    "o1-2024-12-17": (15.00, 60.00),
    "o1-pro": (150.00, 600.00),
    "o1-mini": (1.10, 4.40),
    "o1-mini-2024-09-12": (1.10, 4.40),
    "o3": (2.00, 8.00),
    "o3-pro": (20.00, 80.00),
    "o3-deep-research": (10.00, 40.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    "o4-mini-2025-04-16": (1.10, 4.40),
    "o4-mini-deep-research": (2.00, 8.00),

    # ── Realtime & Audio ───────────────────────────────────────────────
    "gpt-realtime": (4.00, 16.00),
    "gpt-realtime-mini": (0.60, 2.40),
    "gpt-4o-realtime-preview": (5.00, 20.00),
    "gpt-4o-mini-realtime-preview": (0.60, 2.40),
    "gpt-audio": (2.50, 10.00),
    "gpt-audio-mini": (0.60, 2.40),

    # ── Search ─────────────────────────────────────────────────────────
    "gpt-4o-search-preview": (2.50, 10.00),
    "gpt-4o-mini-search-preview": (0.15, 0.60),

    # ── Computer Use ───────────────────────────────────────────────────
    "computer-use-preview": (3.00, 12.00),

    # ── Codex ──────────────────────────────────────────────────────────
    "codex-mini-latest": (1.50, 6.00),

    # ── GPT-4 Turbo (Legacy) ───────────────────────────────────────────
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4-turbo-2024-04-09": (10.00, 30.00),
    "gpt-4-0125-preview": (10.00, 30.00),
    "gpt-4-1106-preview": (10.00, 30.00),

    # ── GPT-4 (Legacy) ─────────────────────────────────────────────────
    "gpt-4": (30.00, 60.00),
    "gpt-4-0613": (30.00, 60.00),
    "gpt-4-0314": (30.00, 60.00),
    "gpt-4-32k": (60.00, 120.00),

    # ── GPT-3.5 Turbo (Legacy) ─────────────────────────────────────────
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-3.5-turbo-0125": (0.50, 1.50),
    "gpt-3.5-turbo-1106": (1.00, 2.00),
    "gpt-3.5-turbo-0613": (1.50, 2.00),
    "gpt-3.5-turbo-instruct": (1.50, 2.00),
    "gpt-3.5-turbo-16k-0613": (3.00, 4.00),
}

# Default fallback price for unknown models
DEFAULT_PRICE: tuple[float, float] = (2.00, 8.00)


def calculate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float:
    """Calculate the cost of an LLM call.

    Args:
        model: The model name (e.g., "gpt-5.2", "o3", "gpt-4o").
        input_tokens: Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.

    Returns:
        Cost in USD.
    """
    input_price, output_price = MODEL_PRICES.get(model, DEFAULT_PRICE)
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return round(cost, 8)


def get_model_price(model: str) -> tuple[float, float]:
    """Get the price per 1M tokens for a model.

    Returns:
        Tuple of (input_price_per_1M, output_price_per_1M).
    """
    return MODEL_PRICES.get(model, DEFAULT_PRICE)
