"""The two-call pipeline, end to end, with both model calls stubbed.

What this pins is the FLOW: that a question becomes a governed selection through two closed
choices, that declining is a first-class outcome, and that the shapes which mix vocabularies
without a deal point cannot be produced at all.

Deliberately no live calls. The accuracy of the two choices is an eval question graded against
a label space; this is the wiring, and wiring is what silently broke three times tonight.
"""

from __future__ import annotations

from explorer.agent.interpret import interpret

DEAL_POINTS = [
    "Knowledge Definition-Answer",
    "Ordinary course efforts standard-Answer",
    "Tail Period Length-Answer",
]


def _run(question, shape, deal_point, points=DEAL_POINTS):
    return interpret(
        question,
        classify=lambda q: shape,
        pick=lambda raw, c: deal_point,
        values=lambda d: points,
    )


class TestALawyersQuestionBecomesASelection:
    def test_is_knowledge_actual_or_constructive(self) -> None:
        s = _run(
            "is knowledge actual or constructive", "distribution", "Knowledge Definition-Answer"
        )
        assert s["measures"] == ["deal_points.n"]
        assert s["dimensions"] == ["deal_points.position"]
        assert s["filters"][0]["values"] == ["Knowledge Definition-Answer"]

    def test_the_efforts_standard_question_that_used_to_return_percentiles(self) -> None:
        """Measured against the free-form path, this question produced median + p25 + p75 over
        seven dimensions. The shape makes that unreachable."""
        s = _run(
            "what's the ordinary course efforts standard",
            "distribution",
            "Ordinary course efforts standard-Answer",
        )
        assert not any("numeric" in m for m in s["measures"])
        assert s["dimensions"] == ["deal_points.position"]

    def test_a_number_question_gets_the_median_shape_with_its_denominator(self) -> None:
        s = _run("what's the typical tail period", "median", "Tail Period Length-Answer")
        assert "deal_points.numeric_n" in s["measures"]
        assert s["filters"][0]["values"] == ["Tail Period Length-Answer"]


class TestDecliningIsAnAnswer:
    def test_a_question_the_corpus_cannot_answer_returns_none(self) -> None:
        """ "What's the average deal size" — deal_value_usd is NULL on all 152 matters. The
        free-form path answered it with `4`, the median of months, business days and percent."""
        assert _run("what's the average deal size", None, None) is None

    def test_a_shape_that_needs_a_deal_point_declines_without_one(self) -> None:
        assert _run("what is market", "distribution", None) is None

    def test_no_vocabulary_means_decline_rather_than_guess(self) -> None:
        assert _run("anything", "distribution", None, points=[]) is None

    def test_coverage_survives_without_a_deal_point(self) -> None:
        """ "How many agreements are loaded" is answerable with no term named."""
        s = _run("how many agreements do we have", "coverage", None)
        assert s is not None
        assert s["filters"] == []


class TestTheChoicesAreClosed:
    def test_the_deal_point_comes_from_the_corpus_not_the_model_text(self) -> None:
        """The picker is offered exactly the corpus's own values, so a deal point that does not
        exist is unrepresentable rather than merely discouraged."""
        seen: list[list[str]] = []

        interpret(
            "anything",
            classify=lambda q: "distribution",
            pick=lambda raw, c: seen.append(list(c)) or c[0],
            values=lambda d: DEAL_POINTS,
        )
        assert seen == [DEAL_POINTS]

    def test_it_asks_for_the_deal_point_dimension_specifically(self) -> None:
        asked: list[str] = []
        interpret(
            "anything",
            classify=lambda q: "distribution",
            pick=lambda raw, c: c[0],
            values=lambda d: asked.append(d) or DEAL_POINTS,
        )
        assert asked == ["deal_points.deal_point_name"]
