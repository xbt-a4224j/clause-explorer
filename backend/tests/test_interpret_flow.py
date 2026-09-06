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
    """One injected chooser: the winning strategy makes both choices in a single call, so the
    test seam is one function rather than two."""
    return interpret(question, choose=lambda q: (shape, deal_point))


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

    def test_only_count_survives_without_a_deal_point(self) -> None:
        """ "How many agreements are loaded" is the `count` shape and needs no term.

        `coverage` without one used to be allowed and should not be: unfiltered it returns
        12,937, the number of labelled ROWS, which reads as an agreement count and is not one.
        A shape that silently changes what it counts is worse than a decline.
        """
        assert (
            interpret(
                "how many agreements do we have",
                choose=lambda q: ("count", None),
                covers=True,
            )
            is not None
        )
        assert _run("how many have an answer", "coverage", None) is None


class TestTheChoicesAreClosed:
    def test_the_deal_point_enum_is_built_from_the_corpus(self) -> None:
        """The guarantee, asserted on the schema itself with no call made: the model chooses
        from the corpus's own deal points, so one that does not exist is undecodable."""
        from explorer.agent.interpret import interpretation_schema

        schema, _ = interpretation_schema({n: ["Yes", "No"] for n in DEAL_POINTS})
        enum = schema["properties"]["deal_point"]["enum"]
        assert set(DEAL_POINTS) <= set(enum)
        assert None in enum, "declining must remain expressible"

    def test_a_quoted_name_is_sanitised_and_maps_back(self) -> None:
        """`strict: true` rejects a double-quote inside an enum literal with a 400, and 16 of
        the 92 ABA names contain one."""
        from explorer.agent.interpret import interpretation_schema

        quoted = 'War, terrorism, natural disasters, "acts of God" or force majeure-Answer'
        schema, safe = interpretation_schema({quoted: ["Yes", "No"]})
        enum = [e for e in schema["properties"]["deal_point"]["enum"] if e]
        assert all('"' not in e for e in enum), "a quote in the enum is a 400 from the API"
        assert safe[enum[0]] == quoted, "and it must map back to the real name"

    def test_a_pick_the_model_says_does_not_cover_the_question_is_dropped(self) -> None:
        """`covers_the_question: false` means the taxonomy has nothing for this — the closest
        deal point is not an answer."""
        assert _run("anything", "distribution", None) is None


class TestAQuestionTheCorpusCannotAnswerNeverReturnsANumber:
    """Caught on the deployed stack, not by the benchmark, which is the point.

    "What's the average deal size in dollars" came back as **152**. The model could find no
    deal point (correct — deal value is NULL on all 152 matters), said so, and then the `count`
    shape ran anyway with no filter and returned the corpus size. A number in answer to a
    question the corpus cannot answer is worse than a refusal, because it looks like an answer.

    The benchmark missed it because it graded the deal point and ignored the shape. A metric
    that reads half the output certifies half the system.

    `covers_the_question: false` now declines outright rather than only clearing the deal
    point. The one shape that legitimately has no deal point — "how many agreements are
    loaded" — is reached by the model returning `count` WITH the flag true.
    """

    def test_the_average_deal_size_question_declines_rather_than_counting(self) -> None:
        assert _run("what's the average deal size in dollars", "count", None) is None

    def test_a_genuine_count_question_still_answers(self) -> None:
        """The flag is about whether the CORPUS can answer, not whether a deal point exists."""
        s = interpret(
            "how many agreements are loaded", choose=lambda q: ("count", None), covers=True
        )
        assert s is not None
        assert s["measures"] == ["comparable_deals.n"]

    def test_a_shape_with_no_deal_point_and_no_coverage_declines(self) -> None:
        for shape in ("distribution", "median", "coverage"):
            assert _run("unanswerable", shape, None) is None, shape
