"""End-to-end shape of filter-value resolution, across every dimension rather than industry.

The old resolver was hardcoded to industry labels — `RESOLVABLE_MEMBERS` was a two-item
frozenset — so every other filter value travelled `verbatim`. Measured before this change, on
the live stack:

    'Healthcare'  on comparable_deals.label            -> n=0   (corpus holds 'Health Care Industry')
    'cash'        on comparable_deals.consideration_type -> n=0   (holds 'All Cash')
    'no-shop'     on deal_points.deal_point_name       -> n=0   (holds a 92-name ABA taxonomy)

Zero rows reads as "we have no comparable deals". That is the failure CLAUDE.md calls the
nastiest in the design, and it was live on /agent/run-selection, the endpoint the UI describes
as "the same path the builder below uses".

These tests pin the pipeline, not the model: the model tier is stubbed everywhere so the suite
stays deterministic and needs no key. What is asserted is that resolution RUNS for every
closed dimension, that an unresolvable value fails loudly instead of returning zero rows, and
that both endpoints behave identically.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from explorer.agent.resolve_filter_value import (
    UnresolvedFilterValue,
    resolve_against,
)

INDUSTRIES = ["Health Care Industry", "Information Industry", "Manufacturing Industry"]
DEAL_POINTS = [
    "Ordinary course efforts standard-Answer",
    "Knowledge Definition-Answer",
    'War, terrorism, natural disasters, "acts of God" or force majeure-Answer (Y/N)',
]


class TestExactMatchNeedsNoModel:
    def test_an_exact_value_resolves_with_no_call(self) -> None:
        calls: list[str] = []
        r = resolve_against(
            "Health Care Industry", INDUSTRIES, pick=lambda *a: calls.append("x") or None
        )
        assert r.resolved == "Health Care Industry"
        assert r.method == "exact"
        assert calls == [], "an exact hit must not spend a model call"

    def test_case_and_whitespace_do_not_matter(self) -> None:
        r = resolve_against("  health care INDUSTRY ", INDUSTRIES, pick=lambda *a: None)
        assert r.resolved == "Health Care Industry"
        assert r.method == "exact"


class TestTheModelTier:
    def test_a_synonym_resolves_through_the_model(self) -> None:
        r = resolve_against("Healthcare", INDUSTRIES, pick=lambda raw, c: "Health Care Industry")
        assert r.resolved == "Health Care Industry"
        assert r.method == "model"

    def test_it_is_offered_only_the_real_candidates(self) -> None:
        """The whole guarantee: the model picks from the corpus's own values, so a value the
        corpus does not carry is not merely discouraged, it is unrepresentable."""
        seen: list[list[str]] = []

        def pick(raw: str, candidates: list[str]) -> str | None:
            seen.append(list(candidates))
            return candidates[0]

        resolve_against("whatever", DEAL_POINTS, pick=pick)
        assert seen == [DEAL_POINTS]

    def test_a_term_of_art_reaches_a_deal_point(self) -> None:
        r = resolve_against(
            "force majeure",
            DEAL_POINTS,
            pick=lambda raw, c: next(x for x in c if "force majeure" in x),
        )
        assert "force majeure" in r.resolved

    def test_the_model_declining_is_a_loud_refusal_not_a_guess(self) -> None:
        """`null` from the model means "the corpus has no deal point for this" — go-shop and
        ticking fee are real terms of art with no MAUD deal point. Refusing beats returning
        the nearest thing, because a false resolution looks like a right answer."""
        with pytest.raises(UnresolvedFilterValue) as excinfo:
            resolve_against("ticking fee", DEAL_POINTS, pick=lambda raw, c: None)
        assert excinfo.value.candidates, "a refusal must carry candidates to pick from"

    def test_a_model_answer_outside_the_candidates_is_rejected(self) -> None:
        """Defence in depth. The enum should make this impossible; if a hallucinated value
        ever arrives it must not become a filter that matches nothing."""
        with pytest.raises(UnresolvedFilterValue):
            resolve_against("healthcare", INDUSTRIES, pick=lambda raw, c: "Healthcare Sector")


class TestItNeverSilentlyReturnsZeroRows:
    @pytest.mark.parametrize(
        "raw,candidates",
        [
            ("Healthcare", INDUSTRIES),
            ("cash", ["All Cash", "All Stock", "Mixed Cash/Stock"]),
            ("no-shop", DEAL_POINTS),
        ],
    )
    def test_an_unresolvable_value_raises_instead_of_filtering(
        self, raw: str, candidates: list[str]
    ) -> None:
        """Every one of these previously travelled verbatim into Cube and returned n=0."""
        with pytest.raises(UnresolvedFilterValue):
            resolve_against(raw, candidates, pick=lambda r, c: None)


class TestBothEndpointsResolveIdentically:
    """The UI under Run the confirmed selection says:

        "Runs through /agent/run-selection, the same path the builder below uses — so the
         validation gate and the min_n refusal still apply."

    That was half true. /agent/ask resolved filter values; /agent/run-selection did not, so the
    same selection behaved differently depending on which button produced it. A claim in the
    interface is not a guarantee; this is.
    """

    SELECTION: ClassVar[dict[str, object]] = {
        "measures": ["deal_points.n"],
        "dimensions": ["deal_points.position"],
        "filters": [
            {
                "member": "deal_points.deal_point_name",
                "operator": "equals",
                "values": ["no-shop"],
            }
        ],
    }

    def test_run_selection_resolves_a_filter_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from explorer.api import run_selection as rs

        monkeypatch.setattr(
            rs, "dimension_values", lambda d: ["Fiduciary exception (no shop)-Answer", "Other"]
        )
        monkeypatch.setattr(rs, "pick_value", lambda raw, c, **k: c[0])
        sent: list[dict] = []
        monkeypatch.setattr(
            rs,
            "cube_query",
            lambda p, timeout=20.0: (
                sent.append(p) or [{"deal_points.position": "Yes", "deal_points.n": "88"}]
            ),
        )
        monkeypatch.setattr(rs, "fetch_vocabulary", lambda: _wide_vocab())

        body = _client().post("/agent/run-selection", json=self.SELECTION).json()
        assert body["refused"] is False
        assert sent[0]["filters"][0]["values"] == ["Fiduciary exception (no shop)-Answer"], (
            "the raw text must never reach Cube — that is what returned n=0"
        )

    def test_an_unresolvable_value_is_a_loud_refusal_not_zero_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from explorer.api import run_selection as rs

        monkeypatch.setattr(rs, "dimension_values", lambda d: ["Something Else-Answer"])
        monkeypatch.setattr(rs, "pick_value", lambda raw, c, **k: None)
        monkeypatch.setattr(rs, "fetch_vocabulary", lambda: _wide_vocab())
        called: list[int] = []
        monkeypatch.setattr(rs, "cube_query", lambda p, timeout=20.0: called.append(1) or [])

        response = _client().post("/agent/run-selection", json=self.SELECTION)
        assert response.status_code == 422
        assert called == [], "an unresolved value must not reach Cube at all"
        assert "no-shop" in response.json()["error"]["message"]

    def test_an_open_dimension_travels_verbatim_and_is_not_blocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Target name grows with the corpus, so it has no vocabulary to lock. Carrying it
        through is right; refusing it would make the resolver a censor."""
        from explorer.api import run_selection as rs

        monkeypatch.setattr(rs, "dimension_values", lambda d: [])
        monkeypatch.setattr(rs, "fetch_vocabulary", lambda: _wide_vocab())
        sent: list[dict] = []
        monkeypatch.setattr(
            rs, "cube_query", lambda p, timeout=20.0: sent.append(p) or [{"deal_points.n": "9"}]
        )
        body = (
            _client()
            .post(
                "/agent/run-selection",
                json={
                    "measures": ["deal_points.n"],
                    "dimensions": [],
                    "filters": [
                        {
                            "member": "comparable_deals.target_name",
                            "operator": "equals",
                            "values": ["ACCELERON PHARMA INC."],
                        }
                    ],
                },
            )
            .json()
        )
        assert body["refused"] is False
        assert sent[0]["filters"][0]["values"] == ["ACCELERON PHARMA INC."]


def _client():
    from explorer.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


def _wide_vocab():
    from explorer.agent.select import Vocabulary

    return Vocabulary(
        measures=("deal_points.n",),
        dimensions=(
            "deal_points.position",
            "deal_points.deal_point_name",
            "comparable_deals.target_name",
        ),
    )
