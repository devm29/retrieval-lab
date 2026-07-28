from __future__ import annotations

from retrieval_lab.llm.base import TokenUsage

# USD per million tokens (input, output). Source: Anthropic pricing, 2026-09.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def price_usage(model: str, input_tokens: int, output_tokens: int) -> TokenUsage:
    input_price, output_price = PRICES.get(model, (0.0, 0.0))
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 8))
