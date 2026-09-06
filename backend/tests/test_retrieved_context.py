"""What the calibration extractor is shown (#58).

The #44 run sent `contract_text[:12000]`. On `contract_10` that is 1.6% of the agreement, and
the MAE definition the question is about first appears at character 328,710 — outside the
window by a factor of twenty-seven. The published "5 of 90 clear the 0.70 gate" was therefore
substantially a measurement of a model that had not been shown the relevant text.

These tests pin the two properties that make the replacement defensible:

* **the window still ends up somewhere the answer can be**, which the synthetic document below
  asserts by putting the defined term past the prefix window and checking that prefix mode
  misses it and retrieval mode finds it; and
* **provenance does not weaken** — a quote is located at its offset in the *whole document*,
  never at its offset inside the window, so `deal_points.source_span_*` and the Label tab's
  drill-through keep meaning the same thing.

Everything here runs with `OPENAI_API_KEY` unset: the embedding cache is a deterministic
bag-of-words stub, the same trick `test_hybrid_retrieval.py` uses with hand-written vectors.
"""

from __future__ import annotations

import hashlib
import itertools

import numpy as np
import pytest
from explorer.evals.context import (
    CONTEXT_CHARS,
    PASSAGE_CHARS,
    Passage,
    PassageIndex,
    locate,
    prefix_passages,
    render,
    retrieval_query,
    split_passages,
)
from explorer.retrieval.embeddings import EmbeddingCache

DIMENSIONS = 64


class BagOfWordsCache(EmbeddingCache):
    """Deterministic vectors with no API and no committed npz.

    Hashing each token into a fixed bucket makes cosine similarity a bag-of-words overlap, which
    is enough structure for "the passage that repeats the query's terms ranks first" to be a
    real assertion rather than an artefact of hand-picked vectors.
    """

    def __init__(self) -> None:
        self.path = None  # type: ignore[assignment]
        self.api_key = None
        self.api_calls = 0
        self._vectors = {}
        self._memory = {}

    def embed_many(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for text in texts:
            vector = np.zeros(DIMENSIONS, dtype=np.float32)
            for token in text.lower().split():
                digest = hashlib.sha1(token.encode("utf-8")).digest()
                vector[digest[0] % DIMENSIONS] += 1.0
            vectors.append(vector)
        return vectors


FILLER = (
    "WHEREAS, the Board of Directors of the Company has approved this Agreement and declared "
    "it advisable and in the best interests of the stockholders of the Company; "
)

DEFINITION = (
    'Section 3.1 "Material Adverse Effect" means any change, event, effect or occurrence that, '
    "individually or in the aggregate, has had or would reasonably be expected to have a "
    "material adverse effect on the ability of the Company to consummate the Merger, excluding "
    "any effect resulting from changes in general economic conditions. "
)


@pytest.fixture
def long_document() -> tuple[str, int]:
    """A document shaped like the finding: recitals first, the defined term far past 12,000."""
    head = FILLER * 2000
    definition_at = len(head)
    return head + DEFINITION + FILLER * 500, definition_at


class TestSplitting:
    def test_every_passage_is_exactly_its_own_byte_range(self) -> None:
        """The offsets are the provenance. If `text[start:end] != passage.text` the whole
        drill-through claim is decorative."""
        text = "abcdefghij" * 500
        for passage in split_passages(text, size=100, stride=60):
            assert text[passage.start : passage.end] == passage.text

    def test_the_split_covers_the_whole_document(self) -> None:
        text = "abcdefghij" * 500
        passages = split_passages(text, size=100, stride=60)
        assert passages[0].start == 0
        assert passages[-1].end == len(text)

    def test_passages_overlap_so_a_sentence_on_a_boundary_survives_whole(self) -> None:
        passages = split_passages("x" * 1000, size=100, stride=60)
        assert passages[1].start < passages[0].end

    def test_a_short_document_is_one_passage(self) -> None:
        assert split_passages("short", size=100, stride=60) == [Passage(0, 5, "short")]


class TestPrefixModeIsStillReproducible:
    def test_it_is_the_first_window_and_nothing_else(self) -> None:
        """The control has to be runnable from the same code, or the before/after table is
        comparing a current run against a remembered one."""
        text = "z" * 50_000
        passages = prefix_passages(text)
        assert len(passages) == 1
        assert (passages[0].start, passages[0].end) == (0, CONTEXT_CHARS)

    def test_a_document_shorter_than_the_window_is_not_padded(self) -> None:
        assert prefix_passages("abc")[0].end == 3


class TestTheQuery:
    def test_it_carries_the_deal_point_name_and_its_answer_vocabulary(self) -> None:
        query = retrieval_query(
            '"Ability to consummate" concept is subject to MAE carveouts', ["Yes", "No"]
        )
        assert "Ability to consummate" in query
        assert "Yes" in query and "No" in query

    def test_a_huge_vocabulary_is_bounded_so_it_cannot_swamp_the_name(self) -> None:
        """One deal point's positions run to 8,512 characters. Pasted whole they dominate the
        BM25 term counts and the deal point being asked about stops mattering."""
        query = retrieval_query("Some deal point", [f"position {i} " * 50 for i in range(80)])
        assert len(query) <= 1000
        assert query.startswith("Some deal point")


class TestLocateReportsWholeDocumentOffsets:
    def test_a_quote_from_a_retrieved_passage_lands_at_its_document_offset(self) -> None:
        """The regression this file exists for. A quote pulled from a passage starting at
        328,710 must not be recorded at offset 42."""
        text = "a" * 5_000 + "the operative sentence." + "b" * 5_000
        passage = Passage(4_900, 5_200, text[4_900:5_200])
        assert locate([passage], text, "the operative sentence.") == (5_000, 5_023)

    def test_a_quote_the_model_invented_is_absent_not_guessed(self) -> None:
        text = "a" * 100
        assert locate([Passage(0, 100, text)], text, "not in the contract") == (None, None)

    def test_an_empty_quote_is_absent(self) -> None:
        assert locate([Passage(0, 3, "abc")], "abc", "") == (None, None)

    def test_a_quote_outside_every_passage_still_resolves_against_the_document(self) -> None:
        """The model can only quote what it was shown, so this is a belt-and-braces path — but
        finding it in the document is strictly better provenance than recording it absent."""
        text = "a" * 1_000 + "elsewhere in the agreement" + "b" * 1_000
        assert locate([Passage(0, 10, text[:10])], text, "elsewhere in the agreement") == (
            1_000,
            1_026,
        )


class TestRendering:
    def test_each_passage_is_labelled_with_its_character_range(self) -> None:
        rendered = render([Passage(100, 110, "0123456789")])
        assert "100" in rendered and "110" in rendered
        assert "0123456789" in rendered

    def test_passages_are_rendered_in_document_order(self) -> None:
        rendered = render([Passage(0, 3, "aaa"), Passage(500, 503, "bbb")])
        assert rendered.index("aaa") < rendered.index("bbb")


class TestRetrievalFindsWhatThePrefixMisses:
    """The issue, as a test."""

    def test_the_prefix_window_does_not_contain_the_definition(
        self, long_document: tuple[str, int]
    ) -> None:
        text, definition_at = long_document
        assert definition_at > CONTEXT_CHARS
        assert "Material Adverse Effect" not in render(prefix_passages(text))

    def test_retrieval_returns_the_passage_holding_the_definition(
        self, long_document: tuple[str, int]
    ) -> None:
        text, definition_at = long_document
        index = PassageIndex(text, cache=BagOfWordsCache())
        passages = index.search(
            retrieval_query(
                '"Ability to consummate" concept is subject to MAE carveouts', ["Yes", "No"]
            )
        )
        rendered = render(passages)
        assert "Material Adverse Effect" in rendered
        assert any(p.start <= definition_at < p.end for p in passages)

    def test_the_retrieved_window_is_no_larger_than_the_prefix_window_it_replaces(
        self, long_document: tuple[str, int]
    ) -> None:
        """What changed is *which* 12,000 characters, not how many. A bigger window would
        confound the comparison with a straightforward context-length effect."""
        text, _ = long_document
        index = PassageIndex(text, cache=BagOfWordsCache())
        passages = index.search(retrieval_query("Material Adverse Effect", ["Yes", "No"]))
        assert sum(p.end - p.start for p in passages) <= CONTEXT_CHARS

    def test_retrieved_passages_come_back_in_document_order(
        self, long_document: tuple[str, int]
    ) -> None:
        text, _ = long_document
        index = PassageIndex(text, cache=BagOfWordsCache())
        passages = index.search(retrieval_query("Material Adverse Effect", ["Yes", "No"]))
        assert [p.start for p in passages] == sorted(p.start for p in passages)

    def test_overlapping_neighbours_are_merged_rather_than_shown_twice(self) -> None:
        """Two adjacent windows share `size - stride` characters. Sending both spends the
        budget on text the model has already read."""
        text = ("material adverse effect " * 100) + ("filler " * 5_000)
        index = PassageIndex(text, cache=BagOfWordsCache())
        passages = index.search(retrieval_query("material adverse effect", ["Yes"]))
        for earlier, later in itertools.pairwise(passages):
            assert earlier.end < later.start

    def test_a_document_smaller_than_the_budget_is_returned_whole(self) -> None:
        text = "one short agreement. " * 20
        index = PassageIndex(text, cache=BagOfWordsCache())
        passages = index.search(retrieval_query("agreement", ["Yes"]))
        assert render(passages).count("one short agreement.") == 20

    def test_the_index_is_built_once_and_reused_across_deal_points(
        self, long_document: tuple[str, int]
    ) -> None:
        """92 deal points per matter. Rebuilding BM25 and re-embedding 700 passages for each
        would be 92x the embedding bill for identical vectors."""
        text, _ = long_document
        index = PassageIndex(text, cache=BagOfWordsCache())
        before = len(index.passages)
        index.search(retrieval_query("first question", ["Yes"]))
        index.search(retrieval_query("second question", ["No"]))
        assert len(index.passages) == before
        assert index.passages[0].end - index.passages[0].start == PASSAGE_CHARS
