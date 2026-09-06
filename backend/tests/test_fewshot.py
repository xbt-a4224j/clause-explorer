"""Few-shot examples for the calibration extractor, drawn from MAUD (#58).

The prompt was zero-shot apart from the option list. These examples are MAUD's own annotated
spans — a lawyer's answer and the byte range they read it at — on matters **outside** the
committed holdout.

The test that matters most is `TestTheHoldoutIsNeverUsed`. A held-out matter appearing in the
prompt would make every accuracy figure in `docs/results/calibration.md` a training-set number
wearing a holdout label, and nothing downstream would look wrong. It is asserted over the whole
vocabulary rather than a sample, because "usually clean" is not a property.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import pytest
from explorer.evals.extract_deal_point import option_ids
from explorer.evals.fewshot import (
    EXAMPLE_MAX_CHARS,
    Example,
    as_messages,
    choose,
    leading_sentence,
    select_examples,
)

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")
ROOT = Path(__file__).resolve().parents[2]
SPLIT = json.loads((ROOT / "docs" / "eval" / "calibration_split.json").read_text())
HOLDOUT = SPLIT["holdout_matter_ids"]


def row(matter_id: str, position: str, length: int = 500) -> tuple[str, str, int, int]:
    return (matter_id, position, 0, length)


class TestLeadingSentence:
    def test_it_is_verbatim_text_from_the_excerpt(self) -> None:
        """The example's quote has to satisfy the same rule the model's answer is graded by:
        locatable in the source by substring search. A paraphrase would teach the opposite."""
        excerpt = "Section 3.1 defines the term. A second sentence follows it here."
        assert leading_sentence(excerpt) in excerpt

    def test_it_stops_at_the_first_sentence_boundary(self) -> None:
        excerpt = "The Merger Consideration is $54.00 in cash, without interest. Then more text."
        assert leading_sentence(excerpt).endswith("without interest.")

    def test_a_sentence_with_no_full_stop_is_bounded_not_unbounded(self) -> None:
        assert len(leading_sentence("word " * 400)) <= 400

    def test_it_never_cuts_a_word_in_half(self) -> None:
        quote = leading_sentence("supercalifragilistic " * 100)
        assert not quote.endswith("supercalifragilist")


class TestChoosingExamples:
    def test_it_prefers_two_different_answers_over_two_of_the_same(self) -> None:
        """Two examples both answering "No" is a prompt that argues for "No"."""
        rows = [row("c1", "No"), row("c2", "No"), row("c3", "Yes")]
        assert [r[1] for r in choose(rows, limit=2)] == ["No", "Yes"]

    def test_a_single_answer_vocabulary_still_yields_examples(self) -> None:
        rows = [row("c1", "No"), row("c2", "No")]
        assert len(choose(rows, limit=2)) == 2

    def test_it_is_deterministic(self) -> None:
        rows = [row("c3", "Yes"), row("c1", "No"), row("c2", "No"), row("c4", "Yes")]
        assert choose(rows, limit=2) == choose(rows, limit=2)

    def test_no_candidates_yields_no_examples_rather_than_an_invented_one(self) -> None:
        assert choose([], limit=2) == []


class TestTheMessages:
    def test_each_example_is_a_user_turn_answered_by_an_assistant_turn(self) -> None:
        options = option_ids(["No", "Yes"])
        example = Example(
            matter_id="contract_130",
            position="Yes",
            start=100,
            end=140,
            excerpt="The parties agree the answer is plainly yes.",
            quote="The parties agree the answer is plainly yes.",
        )
        messages = as_messages([example], options)
        assert [m["role"] for m in messages] == ["user", "assistant"]

    def test_the_answer_is_the_option_id_not_the_free_text_position(self) -> None:
        """The model answers with an id under `strict: true`. An example answering with the
        literal teaches a shape the schema rejects."""
        options = option_ids(["No", "Yes"])
        example = Example("contract_130", "Yes", 0, 10, "some text", "some text")
        answer = json.loads(as_messages([example], options)[1]["content"])
        assert answer["position"] == "p02"
        assert options[answer["position"]] == "Yes"

    def test_the_example_quote_is_locatable_in_the_example_text(self) -> None:
        options = option_ids(["Yes"])
        example = Example("contract_130", "Yes", 0, 20, "alpha beta gamma", "alpha beta")
        user, assistant = as_messages([example], options)
        assert json.loads(assistant["content"])["quote"] in user["content"]

    def test_an_example_whose_position_is_outside_the_option_map_is_dropped(self) -> None:
        """Rather than answered with an id that decodes to nothing."""
        options = option_ids(["Yes"])
        example = Example("contract_130", "Maybe", 0, 10, "text", "text")
        assert as_messages([example], options) == []

    def test_the_user_turn_names_the_matter_and_its_character_range(self) -> None:
        options = option_ids(["Yes"])
        example = Example("contract_130", "Yes", 13320, 13602, "text", "text")
        content = as_messages([example], options)[0]["content"]
        assert "contract_130" in content
        assert "13320" in content and "13602" in content


@pytest.fixture(scope="module")
def selected() -> dict[str, list[Example]]:
    with psycopg.connect(DSN) as conn:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT deal_point_name FROM deal_points ORDER BY deal_point_name"
            ).fetchall()
        ]
    return select_examples(names, HOLDOUT, data_root=ROOT / "data", dsn=DSN)


class TestTheHoldoutIsNeverUsed:
    """Leaking one held-out matter into the prompt invalidates the entire published table."""

    def test_not_one_example_across_the_whole_vocabulary_is_a_holdout_matter(
        self, selected: dict[str, list[Example]]
    ) -> None:
        leaked = {
            (name, example.matter_id)
            for name, examples in selected.items()
            for example in examples
            if example.matter_id in HOLDOUT
        }
        assert leaked == set()

    def test_the_split_file_is_what_defines_held_out(self) -> None:
        assert len(HOLDOUT) == SPLIT["holdout_count"] == 20


class TestAgainstTheRealCorpus:
    def test_every_excerpt_is_the_exact_slice_at_its_recorded_offsets(
        self, selected: dict[str, list[Example]]
    ) -> None:
        """Same provenance rule the product's drill-through follows: the text is the bytes at
        the range, or it is a bug."""
        with psycopg.connect(DSN) as conn:
            sources = dict(conn.execute("SELECT id, source_file FROM matters").fetchall())
        checked = 0
        for examples in selected.values():
            for example in examples:
                text = (ROOT / "data" / sources[example.matter_id]).read_text(
                    encoding="utf-8", errors="replace"
                )
                assert text[example.start : example.end] == example.excerpt
                assert example.quote in example.excerpt
                checked += 1
        assert checked > 0

    def test_excerpts_stay_clause_scale(self, selected: dict[str, list[Example]]) -> None:
        """A document-scale span pasted into the prompt is a table of contents, and it is paid
        for on every one of the run's calls."""
        for examples in selected.values():
            for example in examples:
                assert example.end - example.start <= EXAMPLE_MAX_CHARS

    def test_a_deal_point_with_no_anchored_span_gets_no_examples(
        self, selected: dict[str, list[Example]]
    ) -> None:
        """MAUD anchors a span for some deal points and not others. Where it anchored none on a
        held-in matter, the call stays zero-shot rather than borrowing an example from a
        different question."""
        with psycopg.connect(DSN) as conn:
            unanchored = [
                r[0]
                for r in conn.execute(
                    "SELECT deal_point_name FROM deal_points GROUP BY deal_point_name "
                    "HAVING count(*) FILTER (WHERE span_kind = 'anchored') = 0"
                ).fetchall()
            ]
        assert unanchored, "fixture assumes at least one deal point MAUD never anchored"
        for name in unanchored:
            assert selected.get(name, []) == []
