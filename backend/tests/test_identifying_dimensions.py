"""Grouping by a party name is a k-anonymity bypass, not a query.

Found by an adversarial demo review 2026-09-08. `min_n` gates on counts, and a selection
carrying NO count measure has nothing to gate on — the gate says so in its own docstring and
lets the row through, which is correct for a median-only selection and catastrophic here:

    {"measures": [], "dimensions": ["target_name", "acquirer_name", "position"]}

returned 152 rows of named target, named acquirer and negotiated answer with `refused: false`.
Every row is one agreement, so n=1 by construction and there is no count for the gate to read.
That is the exact disclosure `min_n` exists to prevent, reached by asking for less rather than
more, and it is worse than the aggregate leak already closed because the parties are named.

Filtering TO one party must keep working — the app's own "meant to fail" example does exactly
that and is supposed to refuse at n=1. The bypass is grouping BY the identifying dimension.
"""

from __future__ import annotations

import pytest
from explorer.domain import DOMAIN
from semantic_explorer_base.agent.select import InvalidSelection, Vocabulary, validate_selection

VOCAB = Vocabulary(
    measures=("deal_points.n", "comparable_deals.n"),
    dimensions=(
        "comparable_deals.target_name",
        "comparable_deals.acquirer_name",
        "deal_points.position",
        "comparable_deals.label",
    ),
)


def test_grouping_by_target_name_is_refused() -> None:
    with pytest.raises(InvalidSelection) as caught:
        validate_selection(
            {
                "measures": [],
                "dimensions": [
                    "comparable_deals.target_name",
                    "comparable_deals.acquirer_name",
                    "deal_points.position",
                ],
                "filters": [],
            },
            VOCAB,
            DOMAIN,
        )
    assert "target_name" in str(caught.value)


def test_grouping_by_an_identifying_dimension_is_refused_even_with_a_count() -> None:
    """A count does not rescue it: grouped by one party, every count is 1."""
    with pytest.raises(InvalidSelection):
        validate_selection(
            {
                "measures": ["deal_points.n"],
                "dimensions": ["comparable_deals.target_name", "deal_points.position"],
                "filters": [],
            },
            VOCAB,
            DOMAIN,
        )


def test_filtering_to_one_party_still_validates() -> None:
    """The n=1 refusal is min_n's job and the demo depends on reaching it."""
    validate_selection(
        {
            "measures": ["deal_points.n"],
            "dimensions": ["deal_points.position"],
            "filters": [
                {
                    "member": "comparable_deals.target_name",
                    "operator": "equals",
                    "values": ["TCF FINANCIAL CORPORATION"],
                }
            ],
        },
        VOCAB,
        DOMAIN,
    )


def test_an_ordinary_grouped_selection_still_validates() -> None:
    validate_selection(
        {
            "measures": ["deal_points.n"],
            "dimensions": ["deal_points.position"],
            "filters": [],
        },
        VOCAB,
        DOMAIN,
    )


class TestScopedToOneRecord:
    """`min_n` is a k-anonymity control only if the count it reads is AGREEMENT-grained.

    `deal_points.n` counts answer ROWS — the manifest says it over-counts agreements ~89x. So a
    selection filtered to one named party and grouped by position reported `n=13`, cleared the
    threshold of 5, and served that party's negotiated terms. Same disclosure as the grouping
    bypass, reached through a measure that is legitimately gated for every other selection.

    The fix states the truth the count cannot: a slice pinned to one party contains one
    agreement, so the gate is told the record count directly and refuses on it.
    """

    def test_one_agreement_refuses_even_when_the_answer_count_clears(self) -> None:
        from semantic_explorer_base.gates.min_n import apply as apply_min_n

        result = apply_min_n(
            [{"deal_points.position": "Accurate at MAE standard", "deal_points.n": 13}],
            count_measures=("deal_points.n",),
            min_n=5,
            grouped=True,
            records_in_scope=1,
        )
        assert result.refused is True
        assert result.rows == []
        assert result.n == 1

    def test_a_real_slice_is_unaffected(self) -> None:
        from semantic_explorer_base.gates.min_n import apply as apply_min_n

        result = apply_min_n(
            [{"deal_points.position": "Accurate at MAE standard", "deal_points.n": 143}],
            count_measures=("deal_points.n",),
            min_n=5,
            grouped=True,
            records_in_scope=26,
        )
        assert result.refused is False
        assert len(result.rows) == 1
