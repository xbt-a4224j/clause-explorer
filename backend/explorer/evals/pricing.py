"""Per-token prices, so a run's dollar cost is computed rather than remembered (#44).

CLAUDE.md forbids a plausible invented number anywhere a figure is published, and a model's
price is exactly the kind of number that is easy to half-remember and wrong by 4x. So the table
is small, explicit, and carries the URL it was read from and the date it was read. Adding a
model means reading the page again and updating `PRICE_CHECKED_ON` in the same edit.

An unpriced model raises. Returning 0.0 would write a fabricated "$0.00 measured cost" into a
committed results file, which is worse than failing the run.
"""

from __future__ import annotations

from typing import Final

PRICE_SOURCE: Final = "https://developers.openai.com/api/docs/pricing"
PRICE_CHECKED_ON: Final = "2026-09-03"

# model -> (USD per 1M input tokens, USD per 1M output tokens), standard tier (not batch).
PRICES_USD_PER_MTOK: Final[dict[str, tuple[float, float]]] = {
    "gpt-4o-mini": (0.15, 0.60),
}


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Dollar cost of one call, from its own measured token counts.

    Input and output are priced separately because they differ by 4x on gpt-4o-mini; a blended
    per-token rate would be wrong for every call that is not the exact mix it was blended at.
    """
    if model not in PRICES_USD_PER_MTOK:
        raise KeyError(
            f"No committed price for model {model!r}. Read {PRICE_SOURCE} and add it to "
            "PRICES_USD_PER_MTOK rather than estimating."
        )
    input_rate, output_rate = PRICES_USD_PER_MTOK[model]
    return prompt_tokens / 1e6 * input_rate + completion_tokens / 1e6 * output_rate
