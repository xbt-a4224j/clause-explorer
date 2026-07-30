"""MAUD corpus presence and shape (#7).

The corpus is gitignored, so every test here must skip — never fail — when it is absent, or
CI on a clean checkout goes red for an environment reason. The skip message names the script
that fixes it.

What is asserted is the *shape we are about to build on*: 152 contract texts and the 92 ABA
deal points. If a future MAUD revision changes either, #8's parser assumptions break and this
is where it surfaces.
"""

from __future__ import annotations

import pytest
from explorer.ingest.maud_corpus import (
    contract_paths,
    corpus_available,
    deal_point_names,
    label_csv_paths,
)

needs_corpus = pytest.mark.skipif(
    not corpus_available(),
    reason="MAUD corpus not downloaded — run scripts/download_maud.sh",
)


def test_absence_is_reported_not_raised() -> None:
    """corpus_available() is a bool probe; it must not raise on a clean checkout."""
    assert isinstance(corpus_available(), bool)


@needs_corpus
class TestCorpusShape:
    def test_all_152_contract_texts_present(self) -> None:
        """The HF mirror ships only 100 of these; drill-through needs all 152."""
        assert len(contract_paths()) == 152

    def test_three_label_csvs(self) -> None:
        assert sorted(p.name for p in label_csv_paths()) == [
            "MAUD_dev.csv",
            "MAUD_test.csv",
            "MAUD_train.csv",
        ]

    def test_92_aba_deal_points(self) -> None:
        names = deal_point_names()
        assert len(names) == 92
        assert "Type of Consideration-Answer" in names

    def test_contract_texts_are_non_empty(self) -> None:
        smallest = min(p.stat().st_size for p in contract_paths())
        assert smallest > 10_000
