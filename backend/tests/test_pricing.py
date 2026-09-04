"""Dollar cost of a recorded LLM run (#44).

The calibration run's cost has to be a *measured* number, not a remembered one: tokens come
from `response.usage`, and the per-token price comes from a table that carries the URL and the
date it was read. An unknown model raises rather than defaulting to zero — a silent zero would
put a fabricated $0.00 in a results file, which is exactly what CLAUDE.md's no-fabricated-
numbers rule forbids.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import pytest
from explorer.evals.pricing import PRICE_CHECKED_ON, PRICE_SOURCE, cost_usd


class TestCostUsd:
    def test_input_and_output_are_priced_separately(self) -> None:
        """gpt-4o-mini output costs 4x its input; a single blended rate would understate any
        run with a long completion and overstate this one."""
        input_only = cost_usd("gpt-4o-mini", 1_000_000, 0)
        output_only = cost_usd("gpt-4o-mini", 0, 1_000_000)
        assert input_only == pytest.approx(0.15)
        assert output_only == pytest.approx(0.60)

    def test_a_realistic_call_costs_what_the_table_says(self) -> None:
        # 3,000 prompt tokens + 100 completion tokens.
        assert cost_usd("gpt-4o-mini", 3000, 100) == pytest.approx(
            3000 / 1e6 * 0.15 + 100 / 1e6 * 0.60
        )

    def test_zero_tokens_costs_nothing(self) -> None:
        assert cost_usd("gpt-4o-mini", 0, 0) == 0.0

    def test_an_unpriced_model_raises_rather_than_returning_zero(self) -> None:
        """A silent 0.0 here would be written into a committed results file as a measured
        cost. Refusing is the only honest behaviour."""
        with pytest.raises(KeyError):
            cost_usd("some-model-nobody-priced", 1000, 10)


class TestPriceProvenance:
    def test_the_table_carries_its_source_and_the_date_it_was_read(self) -> None:
        assert PRICE_SOURCE.startswith("https://")
        assert len(PRICE_CHECKED_ON) == 10  # YYYY-MM-DD
