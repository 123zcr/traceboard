"""Model pricing and cost calculation for TraceBoard.

Prices are in USD per 1M tokens as of early 2026.
"""

from __future__ import annotations

# ── Pricing table ──────────────────────────────────────────────────────────
# Format: model_name -> (input_price_per_1M, output_price_per_1M)

MODEL_PRICES: dict[str, tuple[float, float]] = {
    # GPT-4o family
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-11-20": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4o-2024-05-13": (5.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    # GPT-4.1 family
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    # o-series reasoning models
    "o1": (15.00, 60.00),
    "o1-2024-12-17": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o1-mini-2024-09-12": (3.00, 12.00),
    "o3": (10.00, 40.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    # GPT-4 Turbo
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4-turbo-2024-04-09": (10.00, 30.00),
    # GPT-4
    "gpt-4": (30.00, 60.00),
    "gpt-4-0613": (30.00, 60.00),
    # GPT-3.5 Turbo
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-3.5-turbo-0125": (0.50, 1.50),
}

# Default fallback price for unknown models
DEFAULT_PRICE: tuple[float, float] = (2.50, 10.00)


def calculate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float:
    """Calculate the cost of an LLM call.

    Args:
        model: The model name (e.g., "gpt-4o").
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
