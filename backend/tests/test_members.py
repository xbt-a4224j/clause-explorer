"""`POST /agent/members` (#57) — what a selected name means, and whether the corpus can answer.

Ask returned chips reading `measure n`, `measure n`, `has_industry ( )`. Three of #57's four
faults are answered here rather than in the frontend, because all three are questions about
the *corpus* and the frontend has no way to ask them:

**What is this called.** Cube's `/meta` already carries a `title` and a `description` for
every measure and dimension. Rendering the bare member suffix threw both away. A person
confirming a selection cannot confirm what they cannot read.

**What may this hold.** Every dimension in this model is a closed vocabulary — the values are
corpus content, not free text — so a filter on one has a knowable candidate set. Offering a
text box over a closed set invites exactly the error the boolean guard in `ask.py` then has to
catch.

**Can the corpus answer at all.** `deal_value_usd` is NULL on all 152 matters, so
`deal_size_band` holds the single value `unknown`. No selection over either can produce a
figure, and the honest response is to say so rather than hand back a selection to repair. The
check is a corpus probe, not a list of known-empty columns: a column that fills up stops being
reported the moment it does.

This is a separate route from `/agent/ask` on purpose. `ask.py` must never touch Cube's
`/load` — a test there asserts it on every path, and that property is what makes the
confirmation step meaningful. Reading corpus coverage is a query, so it lives here and the
frontend asks for it after the selection comes back.
"""

from __future__ import annotations

from typing import Any

import pytest
from explorer.api import members as members_module
from explorer.api.cube_client import CubeUnavailable
from explorer.api.main import app
from fastapi.testclient import TestClient

META: dict[str, Any] = {
    "cubes": [
        {
            "name": "comparable_deals",
            "title": "Comparable Deals",
            "measures": [
                {
                    "name": "comparable_deals.n",
                    "title": "Comparable Deals N",
                    "type": "count",
                    "description": "THE DENOMINATOR — how many agreements are in the selection.",
                }
            ],
            "dimensions": [
                {
                    "name": "comparable_deals.deal_size_band",
                    "title": "Comparable Deals Deal Size Band",
                    "type": "string",
                    "description": "The single definition of a deal-size band in this system.",
                },
                {
                    "name": "comparable_deals.consideration_type",
                    "title": "Comparable Deals Consideration",
                    "type": "string",
                    "description": "All Cash / All Stock / Mixed.",
                },
                {
                    "name": "comparable_deals.has_industry",
                    "title": "Comparable Deals Has Industry",
                    "type": "boolean",
                    "description": "Whether the matter could be classified at all.",
                },
            ],
        },
        {
            "name": "deal_points",
            "title": "Deal Points",
            "measures": [
                {
                    "name": "deal_points.n",
                    "title": "Deal Points N",
                    "type": "count",
                    "description": "THE DENOMINATOR.",
                },
                {
                    "name": "deal_points.median_numeric_value",
                    "title": "Deal Points Median Numeric Value",
                    "type": "number",
                    "description": "percentile_cont(0.5), never avg.",
                },
            ],
            "dimensions": [],
        },
    ]
}

#: What the corpus actually looks like as loaded, per `docker exec … psql`:
#: every matter lands in the `unknown` band because `deal_value_usd` is NULL for all 152.
ROWS: dict[str, list[dict[str, Any]]] = {
    "comparable_deals.deal_size_band": [
        {"comparable_deals.deal_size_band": "unknown", "comparable_deals.n": 152}
    ],
    "comparable_deals.consideration_type": [
        {"comparable_deals.consideration_type": "All Cash", "comparable_deals.n": 96},
        {"comparable_deals.consideration_type": None, "comparable_deals.n": 21},
        {"comparable_deals.consideration_type": "Mixed", "comparable_deals.n": 35},
    ],
    "comparable_deals.has_industry": [
        {"comparable_deals.has_industry": True, "comparable_deals.n": 139},
        {"comparable_deals.has_industry": False, "comparable_deals.n": 13},
    ],
}


@pytest.fixture
def cube(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stands in for Cube. Records every payload so a test can assert what was asked."""
    seen: list[dict[str, Any]] = []

    def _query(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
        seen.append(payload)
        dimensions = payload.get("dimensions") or []
        if dimensions:
            return ROWS.get(dimensions[0], [])
        measure = (payload.get("measures") or [""])[0]
        # A measure with no dimension is the whole-corpus probe. The median over a column that
        # carries no numbers comes back null, which is the measure-side emptiness signal.
        return [{measure: None if "median" in measure else 152}]

    monkeypatch.setattr(members_module, "meta", lambda: META)
    monkeypatch.setattr(members_module, "cube_query", _query)
    return seen


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _member(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(m for m in body["members"] if m["name"] == name)


class TestTheNameAPersonReads:
    """Fault 1. The chip showed `n`; the catalog has carried `Deal Points N` and a paragraph
    saying what it counts since #36."""

    def test_carries_the_title_from_the_catalog(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post("/agent/members", json={"names": ["deal_points.n"]}).json()
        assert _member(body, "deal_points.n")["title"] == "Deal Points N"

    def test_carries_the_description_from_the_catalog(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post("/agent/members", json={"names": ["deal_points.n"]}).json()
        assert "DENOMINATOR" in _member(body, "deal_points.n")["description"]

    def test_says_whether_a_name_is_a_measure_or_a_dimension(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post(
            "/agent/members",
            json={"names": ["deal_points.n", "comparable_deals.has_industry"]},
        ).json()
        assert _member(body, "deal_points.n")["kind"] == "measure"
        assert _member(body, "comparable_deals.has_industry")["kind"] == "dimension"

    def test_an_unknown_name_is_reported_rather_than_dropped(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        """Silently returning fewer members than were asked for would leave the chip with no
        title and no explanation for why."""
        body = client.post("/agent/members", json={"names": ["comparable_deals.nope"]}).json()
        entry = _member(body, "comparable_deals.nope")
        assert entry["kind"] == "unknown"
        assert entry["title"] == "comparable_deals.nope"


class TestTheValuesADimensionMayHold:
    """Fault 3. Every dimension in this model is a closed vocabulary, so a filter on one has a
    candidate set and never needs a free-text box."""

    def test_a_string_dimension_lists_the_values_the_corpus_holds(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post(
            "/agent/members", json={"names": ["comparable_deals.consideration_type"]}
        ).json()
        entry = _member(body, "comparable_deals.consideration_type")
        assert entry["candidates"] == ["All Cash", "Mixed"]
        assert entry["enumerable"] is True

    def test_a_boolean_dimension_lists_true_and_false(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post(
            "/agent/members", json={"names": ["comparable_deals.has_industry"]}
        ).json()
        entry = _member(body, "comparable_deals.has_industry")
        assert entry["candidates"] == ["false", "true"]

    def test_a_measure_offers_no_candidates(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        """You do not pick a value for a count. Offering one would be a control with nothing
        behind it."""
        body = client.post("/agent/members", json={"names": ["deal_points.n"]}).json()
        entry = _member(body, "deal_points.n")
        assert entry["candidates"] == []
        assert entry["enumerable"] is False

    def test_candidates_are_capped_and_the_cap_is_reported(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, cube: list[dict[str, Any]]
    ) -> None:
        """`deal_points.position` runs to hundreds of answers. A select over hundreds is worse
        than a text box, so past the cap the endpoint says the set was not enumerated rather
        than shipping a truncated list that looks complete."""
        monkeypatch.setattr(members_module, "CANDIDATE_LIMIT", 1)
        body = client.post(
            "/agent/members", json={"names": ["comparable_deals.consideration_type"]}
        ).json()
        entry = _member(body, "comparable_deals.consideration_type")
        assert entry["enumerable"] is False
        assert entry["candidates"] == []
        assert entry["distinct_values"] == 2


class TestSayingTheCorpusCannotAnswer:
    """Fault 4, the one #57 calls interesting. A tool that fails and a tool that explains why
    it cannot answer are different products."""

    def test_a_dimension_with_one_value_corpus_wide_cannot_separate_anything(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post(
            "/agent/members", json={"names": ["comparable_deals.deal_size_band"]}
        ).json()
        entry = _member(body, "comparable_deals.deal_size_band")
        assert entry["cannot_answer"] is not None
        assert "unknown" in entry["cannot_answer"]
        assert "152" in entry["cannot_answer"]

    def test_a_measure_that_is_null_over_the_whole_corpus_cannot_answer(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post(
            "/agent/members", json={"names": ["deal_points.median_numeric_value"]}
        ).json()
        entry = _member(body, "deal_points.median_numeric_value")
        assert entry["cannot_answer"] is not None
        assert "Deal Points Median Numeric Value" in entry["cannot_answer"]

    def test_a_member_the_corpus_can_answer_says_nothing(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post(
            "/agent/members",
            json={"names": ["comparable_deals.consideration_type", "deal_points.n"]},
        ).json()
        assert _member(body, "comparable_deals.consideration_type")["cannot_answer"] is None
        assert _member(body, "deal_points.n")["cannot_answer"] is None

    def test_the_verdict_is_read_from_the_corpus_not_from_a_list_of_column_names(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, cube: list[dict[str, Any]]
    ) -> None:
        """The same dimension stops being reported the moment the data behind it fills in.
        A hardcoded list of known-empty columns would keep reporting it forever."""
        monkeypatch.setitem(
            ROWS,
            "comparable_deals.deal_size_band",
            [
                {"comparable_deals.deal_size_band": "$200M–1B", "comparable_deals.n": 60},
                {"comparable_deals.deal_size_band": "> $1B", "comparable_deals.n": 92},
            ],
        )
        body = client.post(
            "/agent/members", json={"names": ["comparable_deals.deal_size_band"]}
        ).json()
        assert _member(body, "comparable_deals.deal_size_band")["cannot_answer"] is None

    def test_coverage_carries_its_denominator(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        """Every number in this product carries the denominator it was computed over."""
        body = client.post(
            "/agent/members", json={"names": ["comparable_deals.consideration_type"]}
        ).json()
        entry = _member(body, "comparable_deals.consideration_type")
        assert entry["populated"] == 131
        assert entry["total"] == 152


class TestFailureIsAState:
    def test_cube_down_is_503_not_an_empty_answer(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ "Nothing is known about this member" and "the semantic layer is unreachable" are
        different statements, and the chip renders them differently."""

        def boom() -> dict[str, Any]:
            raise CubeUnavailable("down")

        monkeypatch.setattr(members_module, "meta", boom)
        assert client.post("/agent/members", json={"names": ["deal_points.n"]}).status_code == 503

    def test_no_names_is_an_empty_list_not_an_error(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        body = client.post("/agent/members", json={"names": []}).json()
        assert body["members"] == []
        assert cube == []

    def test_a_repeated_name_is_probed_once(
        self, client: TestClient, cube: list[dict[str, Any]]
    ) -> None:
        """The model duplicated `comparable_deals.n` in the selection that opened #57. One
        chip, and one query behind it."""
        body = client.post(
            "/agent/members", json={"names": ["deal_points.n", "deal_points.n"]}
        ).json()
        assert len(body["members"]) == 1
        assert len(cube) == 1
