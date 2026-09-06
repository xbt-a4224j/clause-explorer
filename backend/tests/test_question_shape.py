"""Question shape: pick the SKELETON first, then only the deal point.

Measured before this existed, on ten questions a transactional lawyer would actually ask,
0 of 10 produced an answer to the question asked. The failures were not subtle:

    "what percentage of deals is cash-only"      -> comparable_deals.n        (a count, no denominator)
    "what's the largest deal value"              -> comparable_deals.n        (a count, not a max)
    "what's the ordinary course efforts standard"-> median + p25 + p75 over 7 dimensions

Every one is the same mistake: given a free choice over eleven measures, the model picks a
plausible one that does not answer the question. But almost every "what's market" question has
one skeleton — count the agreements, grouped by their answer, filtered to one deal point. If
the shape is chosen from a four-value enum first, the model never picks the measure for that
case, and the whole class of error stops being reachable.

The shape is the cheap decision and the deal point is the hard one. Separating them means the
hard one gets the model's full attention against a closed vocabulary.
"""

from __future__ import annotations

import pytest
from explorer.agent.shape import SHAPES, selection_for


class TestTheDistributionSkeleton:
    """The overwhelmingly common legal question: how did this term come out across the set."""

    def test_it_counts_agreements_grouped_by_their_answer(self) -> None:
        s = selection_for("distribution", deal_point="Knowledge Definition-Answer")
        assert s["measures"] == ["deal_points.n"]
        assert s["dimensions"] == ["deal_points.position"]

    def test_it_pins_the_deal_point(self) -> None:
        s = selection_for("distribution", deal_point="Knowledge Definition-Answer")
        f = s["filters"][0]
        assert f["member"] == "deal_points.deal_point_name"
        assert f["values"] == ["Knowledge Definition-Answer"]

    def test_it_never_selects_a_percentile(self) -> None:
        """A percentile over `numeric_value` mixes months, business days and percent unless it
        is scoped, and the shape for "what is the standard" is a distribution, not an average."""
        s = selection_for("distribution", deal_point="Ordinary course efforts standard-Answer")
        assert not any("numeric" in m for m in s["measures"])


class TestTheMedianSkeleton:
    def test_it_carries_its_denominator(self) -> None:
        """A median with no n is a figure nobody can weigh. CLAUDE.md: every number carries
        its denominator, always, everywhere."""
        s = selection_for("median", deal_point="Tail Period Length-Answer")
        assert "deal_points.median_numeric_value" in s["measures"]
        assert "deal_points.numeric_n" in s["measures"]

    def test_it_is_scoped_so_the_units_cannot_mix(self) -> None:
        """Satisfies REQUIRES_SCOPE by construction rather than by luck."""
        from explorer.agent.select import REQUIRES_SCOPE, Vocabulary, validate_selection

        s = selection_for("median", deal_point="Tail Period Length-Answer")
        vocab = Vocabulary(
            measures=tuple(s["measures"]) + tuple(REQUIRES_SCOPE),
            dimensions=("deal_points.deal_point_name", "deal_points.position"),
        )
        validate_selection(s, vocab)  # must not raise


class TestTheCountSkeleton:
    def test_a_bare_count_needs_no_deal_point(self) -> None:
        """ "How many agreements are there" is answerable without naming a term."""
        s = selection_for("count", deal_point=None)
        assert s["measures"] == ["comparable_deals.n"]
        assert s["filters"] == []


class TestTheShapesAreClosedAndSmall:
    def test_every_shape_is_buildable(self) -> None:
        for shape in SHAPES:
            s = selection_for(shape, deal_point="Knowledge Definition-Answer")
            assert s["measures"], f"{shape} produced no measure"

    def test_an_unknown_shape_is_refused_not_guessed(self) -> None:
        with pytest.raises(KeyError):
            selection_for("vibes", deal_point=None)

    def test_a_distribution_without_a_deal_point_is_refused(self) -> None:
        """Grouping by position across all 92 deal points mixes every answer vocabulary in the
        corpus into one column — the same class of nonsense as an unscoped percentile."""
        with pytest.raises(ValueError, match="deal point"):
            selection_for("distribution", deal_point=None)
