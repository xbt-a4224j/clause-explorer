"""`POST /agent/ask` (#47) — free text in, a *selection* out, never an answer.

The repo's central claim is that a model is constrained to select from a governed vocabulary
rather than to generate SQL or state a figure. Before this endpoint that claim was only
reachable from the eval harness: nothing a user could touch ever called a model. These tests
are about the two properties that make the claim checkable rather than asserted.

**The model emits no number.** Not "is unlikely to" — `numeric_leaves()` walks the raw decoded
model output and the route refuses anything carrying an int or a float. The `needs_key` test at
the bottom asserts the same property against a real call.

**Nothing executes.** `/agent/ask` never touches Cube's `/load`. It resolves, validates, and
returns chips; execution stays behind the user's confirmation on `/agent/run-selection`, where
the `min_n` gate already lives. A test asserts Cube was never queried on any path here,
including the reject paths.

Filter-value resolution is the third property. A value the corpus does not carry must fail
loudly with its near misses attached rather than becoming a filter that returns zero rows —
"no comparable deals" and "you named an industry we do not have" are different statements.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.agent.select import Vocabulary
from explorer.api import ask as ask_module
from explorer.api.main import app
from explorer.evals.pricing import PRICE_CHECKED_ON, PRICE_SOURCE, cost_usd
from fastapi.testclient import TestClient

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

FAKE_META = {
    "cubes": [
        {
            "name": "comparable_deals",
            "measures": [{"name": "comparable_deals.n"}],
            "dimensions": [
                {"name": "comparable_deals.label"},
                {"name": "comparable_deals.consideration_type"},
            ],
        },
        {
            "name": "deal_points",
            "measures": [{"name": "deal_points.n"}, {"name": "deal_points.present_count"}],
            "dimensions": [
                {"name": "deal_points.deal_point_name"},
                {"name": "deal_points.position"},
            ],
        },
    ]
}

VOCABULARY = Vocabulary(
    measures=("comparable_deals.n", "deal_points.n", "deal_points.present_count"),
    dimensions=(
        "comparable_deals.label",
        "comparable_deals.consideration_type",
        "comparable_deals.has_industry",
        "deal_points.deal_point_name",
        "deal_points.position",
    ),
    dimension_types=(
        ("comparable_deals.label", "string"),
        ("comparable_deals.consideration_type", "string"),
        ("comparable_deals.has_industry", "boolean"),
        ("deal_points.deal_point_name", "string"),
        ("deal_points.position", "string"),
    ),
)


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM industries").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_corpus = pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def no_cube(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Records every Cube `/load` call. `/agent/ask` must make none — it selects, it does not
    execute, and the difference is the whole confirmation step."""
    calls: list[dict] = []

    def _fail(payload: dict, timeout: float = 20.0) -> list[dict]:
        calls.append(payload)
        raise AssertionError("/agent/ask executed a query; it must only select.")

    monkeypatch.setattr(ask_module, "cube_query", _fail, raising=False)
    return calls


def stub_model(monkeypatch: pytest.MonkeyPatch, selection: dict) -> None:
    """Stands in for the one call that leaves the process. Every test below exercises the
    validation, resolution and refusal paths with no key and no network."""
    monkeypatch.setattr(ask_module, "fetch_vocabulary", lambda: VOCABULARY)

    def _select(question: str, vocabulary: Vocabulary, api_key: str) -> ask_module.SelectionCall:
        return ask_module.SelectionCall(
            selection=selection,
            model="gpt-4o-mini",
            prompt_tokens=2104,
            completion_tokens=61,
            latency_ms=1412.0,
        )

    monkeypatch.setattr(ask_module, "select_with_usage", _select)
    monkeypatch.setattr(ask_module.settings, "openai_api_key", "test-key-not-real")


class TestTheModelNeverEmitsANumber:
    """The one property the whole design rests on. A selection is names; the figure is
    Postgres's job."""

    def test_a_numeric_leaf_anywhere_in_the_model_output_is_refused(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.n"],
                "dimensions": [],
                # a model that answers instead of selecting
                "filters": [
                    {"member": "deal_points.n", "operator": "equals", "values": ["19"], "n": 19}
                ],
                "timeDimensions": [],
            },
        )
        response = client.post("/agent/ask", json={"question": "how many"})
        assert response.status_code == 422
        assert "number" in response.json()["error"]["message"].lower()

    def test_numeric_leaves_finds_ints_floats_and_bools_at_any_depth(self) -> None:
        assert ask_module.numeric_leaves({"a": {"b": [{"c": 3}]}}) == ["a.b[0].c"]
        assert ask_module.numeric_leaves({"a": 1.5}) == ["a"]
        # a string that looks like a number is still a string — the schema allows those as
        # filter values, and "2021" is a legitimate signing year
        assert ask_module.numeric_leaves({"values": ["2021"]}) == []


class TestNothingExecutes:
    def test_a_valid_question_returns_chips_and_never_queries_cube(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.present_count", "deal_points.n"],
                "dimensions": ["deal_points.position"],
                "filters": [],
                "timeDimensions": [],
            },
        )
        response = client.post("/agent/ask", json={"question": "fiduciary outs"})
        assert response.status_code == 200
        body = response.json()
        assert body["measures"] == ["deal_points.present_count", "deal_points.n"]
        assert body["dimensions"] == ["deal_points.position"]
        assert body["runnable"] is True
        assert no_cube == []

    def test_the_response_carries_no_result_and_no_figure(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.n"],
                "dimensions": [],
                "filters": [],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "how many"}).json()
        assert "rows" not in body
        assert "n" not in body


class TestOutOfVocabularyIsRejectedBeforeExecution:
    """Structurally impossible given the enum-constrained schema — checked anyway, because a
    schema bug or a model ignoring the schema must not reach Cube."""

    def test_an_unknown_measure_is_a_422_and_names_the_offender(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.invented_measure"],
                "dimensions": [],
                "filters": [],
                "timeDimensions": [],
            },
        )
        response = client.post("/agent/ask", json={"question": "anything"})
        assert response.status_code == 422
        assert "invented_measure" in response.json()["error"]["message"]
        assert no_cube == []

    def test_an_unknown_filter_member_is_rejected_too(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.n"],
                "dimensions": [],
                "filters": [
                    {"member": "matters.secret_column", "operator": "equals", "values": ["x"]}
                ],
                "timeDimensions": [],
            },
        )
        response = client.post("/agent/ask", json={"question": "anything"})
        assert response.status_code == 422
        assert no_cube == []


@needs_corpus
class TestFilterValuesFailLoudly:
    """The nastiest failure mode in the design: a value the corpus does not carry becomes a
    filter that returns zero rows, which reads as "we have no comparable deals"."""

    def test_an_exact_industry_label_resolves_and_carries_its_matter_count(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "comparable_deals.label",
                        "operator": "equals",
                        "values": ["Health Care Industry"],
                    }
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "healthcare deals"}).json()
        resolution = body["filters"][0]["resolutions"][0]
        assert resolution["method"] == "exact"
        assert resolution["resolved"] == "Health Care Industry"
        assert resolution["matter_count"] == 26
        assert body["runnable"] is True

    def test_a_near_miss_resolves_by_embedding_and_reports_its_similarity(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "comparable_deals.label",
                        "operator": "equals",
                        "values": ["healthcare"],
                    }
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "healthcare deals"}).json()
        resolution = body["filters"][0]["resolutions"][0]
        assert resolution["method"] == "embedding"
        assert resolution["resolved"] == "Health Care Industry"
        assert resolution["similarity"] is not None
        # the confirmed filter carries the corpus's own label, not what the model typed
        assert body["filters"][0]["values"] == ["Health Care Industry"]

    def test_a_value_the_corpus_does_not_carry_blocks_the_run_and_lists_near_misses(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "comparable_deals.label",
                        "operator": "equals",
                        "values": ["not a real industry at all"],
                    }
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "unicorn deals"}).json()
        resolution = body["filters"][0]["resolutions"][0]
        assert resolution["method"] == "unresolved"
        assert len(resolution["candidates"]) > 0
        # loud: the run is blocked with a stated reason, not a query returning zero rows
        assert body["runnable"] is False
        assert "not a real industry at all" in body["blocked_reason"]
        assert no_cube == []

    def test_a_member_the_ladder_does_not_cover_passes_through_marked_verbatim(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        """The ladder resolves industry labels; every other value is the model's text. Saying
        so on the chip beats implying a resolution that never happened."""
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "comparable_deals.consideration_type",
                        "operator": "equals",
                        "values": ["All Cash"],
                    }
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "cash deals"}).json()
        resolution = body["filters"][0]["resolutions"][0]
        assert resolution["method"] == "verbatim"
        assert resolution["note"]
        assert body["runnable"] is True


class TestAStringOnABooleanDimensionCannotMatch:
    """Not the model's judgement but its arithmetic: `has_industry` is yes/no, so no row can
    hold "Aerospace". Cube answers zero rows, which reads as "we have no comparable deals".

    This is the observed live failure, not a hypothetical. On 2026-09-05 the model filtered
    `has_industry = "Aerospace"` for "how many aerospace deals do we have", and with that
    dimension taken out of its choices it moved to `is_inferred_industry` — it is matching the
    word "industry" in the name. A type check catches it wherever it lands.
    """

    def test_a_string_on_a_boolean_dimension_blocks_the_run(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "comparable_deals.has_industry",
                        "operator": "equals",
                        "values": ["Aerospace"],
                    }
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "aerospace deals"}).json()
        resolution = body["filters"][0]["resolutions"][0]
        assert resolution["method"] == "unresolved"
        assert resolution["candidates"] == ["true", "false"]
        assert body["runnable"] is False
        assert "yes/no" in body["blocked_reason"]
        assert no_cube == []

    def test_a_genuine_boolean_value_passes(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "comparable_deals.has_industry",
                        "operator": "equals",
                        "values": ["true"],
                    }
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "classified deals"}).json()
        assert body["runnable"] is True

    def test_the_types_come_from_cube_meta_rather_than_a_list_here(self) -> None:
        """A hardcoded list of boolean dimensions is a second definition of the Cube model,
        and the one that would go stale."""
        from explorer.agent.select import fetch_vocabulary

        vocabulary = fetch_vocabulary(
            cube_meta={
                "cubes": [
                    {
                        "name": "comparable_deals",
                        "measures": [],
                        "dimensions": [
                            {"name": "comparable_deals.has_industry", "type": "boolean"},
                            {"name": "comparable_deals.label", "type": "string"},
                        ],
                    }
                ]
            }
        )
        assert vocabulary.type_of("comparable_deals.has_industry") == "boolean"
        assert vocabulary.type_of("comparable_deals.label") == "string"


class TestAMissingKeyIsAClearError:
    """No keyless-boot promise since 7bc47ee — a key is required to run the product. What is
    still ordinary engineering: say which variable is unset, and never put key material in the
    message."""

    def test_no_key_is_a_503_naming_the_variable(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        monkeypatch.setattr(ask_module, "fetch_vocabulary", lambda: VOCABULARY)
        monkeypatch.setattr(ask_module.settings, "openai_api_key", None)
        response = client.post("/agent/ask", json={"question": "anything"})
        assert response.status_code == 503
        detail = response.json()["error"]["message"]
        assert "OPENAI_API_KEY" in detail
        assert "sk-" not in detail


class TestWhatTheQuestionCost:
    """#50. Every field measured: the token counts come off the response, the dollars off the
    committed price table with its checked-on date. Nothing here is a remembered rate."""

    def test_the_response_carries_every_usage_field(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {"measures": ["deal_points.n"], "dimensions": [], "filters": [], "timeDimensions": []},
        )
        usage = client.post("/agent/ask", json={"question": "how many"}).json()["usage"]
        assert usage["model"] == "gpt-4o-mini"
        assert usage["prompt_tokens"] == 2104
        assert usage["completion_tokens"] == 61
        assert usage["latency_ms"] == 1412.0
        assert usage["price_checked_on"] == PRICE_CHECKED_ON
        assert usage["price_source"] == PRICE_SOURCE

    def test_cost_is_priced_from_the_committed_table_not_hardcoded(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        """Asserted against `cost_usd` rather than a literal: a literal here would be a second
        copy of the price table, and the one that goes stale silently."""
        stub_model(
            monkeypatch,
            {"measures": ["deal_points.n"], "dimensions": [], "filters": [], "timeDimensions": []},
        )
        usage = client.post("/agent/ask", json={"question": "how many"}).json()["usage"]
        assert usage["cost_usd"] == cost_usd("gpt-4o-mini", 2104, 61)

    def test_an_unpriced_model_raises_rather_than_reporting_zero(self) -> None:
        """A "$0.00 measured cost" in the UI would be a fabricated number, which CLAUDE.md
        ranks as worse than a blank."""
        with pytest.raises(KeyError):
            cost_usd("gpt-5-imaginary", 10, 10)

    def test_the_cost_is_reported_even_though_nothing_was_executed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        """The dollars were spent at the question, not at the run — so they are reported by
        the endpoint that spent them, whether or not a selection is ever executed."""
        stub_model(
            monkeypatch,
            {"measures": [], "dimensions": [], "filters": [], "timeDimensions": []},
        )
        body = client.post("/agent/ask", json={"question": "unanswerable"}).json()
        assert body["measures"] == []
        assert body["usage"]["cost_usd"] > 0


class TestTheCallIsLogged:
    def test_model_tokens_and_latency_are_logged(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        no_cube: list[dict],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.n"],
                "dimensions": [],
                "filters": [],
                "timeDimensions": [],
            },
        )
        with caplog.at_level("INFO"):
            client.post("/agent/ask", json={"question": "how many"})
        logged = "\n".join(r.getMessage() for r in caplog.records)
        assert "agent_ask" in logged
        assert "gpt-4o-mini" in logged
        assert "2104" in logged
        assert "cost_usd" in logged


@pytest.mark.needs_key
class TestLiveAsk:
    """One real call, end to end: question in, selection out, no numeric field anywhere.

    Deliberately **not** asserting that the model selected well, or selected anything at all.
    Measured over four probe calls on 2026-09-05 the same question produced an empty selection
    once and the entire 11-measure, 18-dimension vocabulary once — and `measure_selection.json`
    already scores that judgement properly, at 0.80 measure precision and 0.20 refusal
    accuracy. Asserting on it here would be a flaky duplicate of #27's eval. What this route
    owes is structural and holds on every one of those outcomes: a selection came back, and it
    carries no figure.
    """

    def test_a_question_returns_a_selection_with_no_number_in_it(self, client: TestClient) -> None:
        response = client.post(
            "/agent/ask",
            json={"question": "healthcare all-cash deals, what did boards get on fiduciary outs"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        # a selection, not an answer: the four selection keys and nothing computed
        assert set(body["model_selection"]) == {
            "measures",
            "dimensions",
            "filters",
            "timeDimensions",
        }
        assert "rows" not in body
        assert ask_module.numeric_leaves(body["model_selection"]) == []


class TestTheSelectionIsCollapsedBeforeItIsRendered:
    """#57 fault 2. Asked "What's the average deal size for healthcare?" the model selected
    `comparable_deals.n` twice and the UI drew the chip twice. That is the model being sloppy
    and the response faithfully reproducing the sloppiness — a duplicate name selects nothing
    a single one does not, so it is collapsed here rather than in one client."""

    def test_a_repeated_measure_becomes_one(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n", "comparable_deals.n"],
                "dimensions": [],
                "filters": [],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "average deal size"}).json()
        assert body["measures"] == ["comparable_deals.n"]

    def test_a_repeated_dimension_becomes_one(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.n"],
                "dimensions": ["deal_points.position", "deal_points.position"],
                "filters": [],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "positions"}).json()
        assert body["dimensions"] == ["deal_points.position"]

    def test_selection_order_survives_the_collapse(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        """First occurrence wins. Re-sorting would make the chips disagree with the model's
        own output shown beside them."""
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.present_count", "deal_points.n", "deal_points.n"],
                "dimensions": [],
                "filters": [],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "prevalence"}).json()
        assert body["measures"] == ["deal_points.present_count", "deal_points.n"]

    def test_two_identical_filters_become_one(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "deal_points.position",
                        "operator": "equals",
                        "values": ["All Cash"],
                    },
                    {
                        "member": "deal_points.position",
                        "operator": "equals",
                        "values": ["All Cash"],
                    },
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "cash deals"}).json()
        assert len(body["filters"]) == 1

    def test_two_filters_on_one_member_with_different_values_both_survive(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        """Collapsing these would silently drop half of what was asked for, which is a worse
        failure than showing two chips."""
        stub_model(
            monkeypatch,
            {
                "measures": ["deal_points.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "deal_points.position",
                        "operator": "equals",
                        "values": ["All Cash"],
                    },
                    {"member": "deal_points.position", "operator": "equals", "values": ["Mixed"]},
                ],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "cash or mixed"}).json()
        assert len(body["filters"]) == 2

    def test_the_model_output_is_still_echoed_verbatim(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, no_cube: list[dict]
    ) -> None:
        """The chips are the cleaned reading; `model_selection` is what the model actually
        said. Collapsing both would hide the sloppiness instead of handling it."""
        stub_model(
            monkeypatch,
            {
                "measures": ["comparable_deals.n", "comparable_deals.n"],
                "dimensions": [],
                "filters": [],
                "timeDimensions": [],
            },
        )
        body = client.post("/agent/ask", json={"question": "average deal size"}).json()
        assert body["model_selection"]["measures"] == [
            "comparable_deals.n",
            "comparable_deals.n",
        ]
