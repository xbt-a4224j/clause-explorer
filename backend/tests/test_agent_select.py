"""NL -> Cube selection (#24).

The engineering claim: an agent has two independent ways to be wrong — the number and the
definition of the number. Enum-constraining the selection closes the second at decode time; the
tests here are about proving that constraint actually holds, not about testing the LLM's
judgement (that is #27's eval).

No API call in the no-key gate: the vocabulary parser, the validator, and the route's rejection
path are all pure and exercised with a stub selection. `TestLiveAgent` at the bottom is the one
real call, marked `needs_key`.
"""

from __future__ import annotations

import pytest
from explorer.agent import select as select_module
from explorer.agent.select import (
    InvalidSelection,
    Vocabulary,
    fetch_vocabulary,
    validate_selection,
)
from explorer.api.main import app
from fastapi.testclient import TestClient

FAKE_META = {
    "cubes": [
        {
            "name": "comparable_deals",
            "measures": [{"name": "comparable_deals.n"}],
            "dimensions": [{"name": "comparable_deals.label"}, {"name": "comparable_deals.code"}],
        },
        {
            "name": "deal_points",
            "measures": [{"name": "deal_points.present_count"}],
            "dimensions": [{"name": "deal_points.deal_point_name"}],
        },
        # not agent-selectable — dimension metadata, not a fact table
        {
            "name": "folio_concepts",
            "measures": [],
            "dimensions": [{"name": "folio_concepts.label"}],
        },
    ]
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestVocabularyIsReadFromMeta:
    def test_measures_and_dimensions_come_from_the_selectable_cubes(self) -> None:
        vocab = fetch_vocabulary(cube_meta=FAKE_META)
        assert "comparable_deals.n" in vocab.measures
        assert "deal_points.present_count" in vocab.measures
        assert "comparable_deals.label" in vocab.dimensions

    def test_the_do_not_use_for_market_measure_is_never_selectable(self) -> None:
        """The model file names it that way specifically so it isn't reached for casually
        (#27's eval measured a live model doing exactly that when asked for "the average
        reverse termination fee"). Structural exclusion, not just a scary name."""
        meta = {
            "cubes": [
                {
                    "name": "deal_points",
                    "measures": [
                        {"name": "deal_points.mean_numeric_value_do_not_use_for_market"},
                        {"name": "deal_points.median_numeric_value"},
                    ],
                    "dimensions": [],
                }
            ]
        }
        vocab = fetch_vocabulary(cube_meta=meta)
        assert "deal_points.mean_numeric_value_do_not_use_for_market" not in vocab.measures
        assert "deal_points.median_numeric_value" in vocab.measures

    def test_non_selectable_cubes_are_excluded(self) -> None:
        """folio_concepts is dimension metadata, not a fact table an agent aggregates over."""
        vocab = fetch_vocabulary(cube_meta=FAKE_META)
        assert "folio_concepts.label" not in vocab.dimensions

    def test_a_meta_change_changes_the_vocabulary_with_no_code_change(self) -> None:
        """The vocabulary is never hardcoded — a new measure in Cube's model is immediately
        selectable, and a renamed one immediately stops being."""
        meta = {
            "cubes": [
                {
                    "name": "comparable_deals",
                    "measures": [{"name": "comparable_deals.brand_new_measure"}],
                    "dimensions": [],
                }
            ]
        }
        vocab = fetch_vocabulary(cube_meta=meta)
        assert vocab.measures == ("comparable_deals.brand_new_measure",)


class TestEnumConstrainedSchema:
    def test_the_json_schema_enumerates_exactly_the_known_measures(self) -> None:
        vocab = Vocabulary(measures=("a.n",), dimensions=("a.label",))
        props = vocab.as_json_schema_properties()
        assert props["measures"]["items"]["enum"] == ["a.n"]
        assert props["dimensions"]["items"]["enum"] == ["a.label"]

    def test_filter_member_enum_covers_measures_and_dimensions(self) -> None:
        vocab = Vocabulary(measures=("a.n",), dimensions=("a.label",))
        props = vocab.as_json_schema_properties()
        assert set(props["filters"]["items"]["properties"]["member"]["enum"]) == {
            "a.n",
            "a.label",
        }


class TestServerSideValidation:
    """The schema should make an invalid name unrepresentable at decode time; this is the
    gate every selection passes through regardless, in case the model or the schema misbehaves."""

    def test_a_valid_selection_passes(self) -> None:
        vocab = fetch_vocabulary(cube_meta=FAKE_META)
        validate_selection(
            {"measures": ["comparable_deals.n"], "dimensions": [], "filters": []}, vocab
        )  # does not raise

    def test_an_unknown_measure_is_rejected(self) -> None:
        vocab = fetch_vocabulary(cube_meta=FAKE_META)
        with pytest.raises(InvalidSelection):
            validate_selection({"measures": ["made_up.measure"], "dimensions": []}, vocab)

    def test_an_unknown_filter_member_is_rejected(self) -> None:
        vocab = fetch_vocabulary(cube_meta=FAKE_META)
        with pytest.raises(InvalidSelection):
            validate_selection(
                {
                    "measures": [],
                    "dimensions": [],
                    "filters": [{"member": "nonsense", "operator": "equals", "values": ["x"]}],
                },
                vocab,
            )


class TestTheHttpSurfaceIsGone:
    """#45 — `POST /agent/select` and `POST /agent/resolve-filter-value` were never called by
    anything. The UI drives `/agent/run-selection`, and the eval imports `select_via_llm` and
    `resolve_filter_value` directly. The functions stay and are tested above and in
    `test_filter_resolution.py`; only the HTTP surface is deleted, so the routes must 404.

    The property those route tests carried — no number reaches a response from the model —
    is still asserted structurally, on the route that survives, in `test_run_selection.py`.
    """

    def test_select_is_no_longer_routed(self, client: TestClient) -> None:
        assert client.post("/agent/select", json={"question": "anything"}).status_code == 404

    def test_resolve_filter_value_is_no_longer_routed(self, client: TestClient) -> None:
        assert client.post("/agent/resolve-filter-value", json={"value": "x"}).status_code == 404


@pytest.mark.needs_key
class TestLiveAgent:
    """The one real call in this file. Everything else in the file runs with no key."""

    def test_a_real_question_produces_a_valid_enum_constrained_selection(self) -> None:
        from explorer.api.settings import settings

        if not settings.has_openai_key:
            pytest.skip("OPENAI_API_KEY not set")

        vocab = fetch_vocabulary()
        selection = select_module.select_via_llm(
            "how many matters are there", vocab, settings.openai_api_key
        )
        validate_selection(selection, vocab)  # does not raise: proves the enum held live
        assert selection["measures"]
