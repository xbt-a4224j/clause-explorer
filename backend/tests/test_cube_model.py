"""The Cube model is an API, so it gets contract tests (#12).

Measure names here are the agent's label space (#24) and the eval's fixtures (#27). A rename
is a breaking change. These tests assert the properties that make the model safe to point an
LLM at — they are cheap to run and they fail loudly when someone "tidies" the YAML.

The static tests read the file and never need Cube running. The live test queries the REST
API and skips when it is not up.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
import yaml

MODEL_DIR = Path(__file__).resolve().parents[2] / "cube" / "model"
DEAL_POINTS = MODEL_DIR / "deal_points.yml"
CUBE_URL = os.getenv("CUBE_API_URL", "http://localhost:4000/cubejs-api/v1")


@pytest.fixture(scope="module")
def model() -> dict:
    return yaml.safe_load(DEAL_POINTS.read_text(encoding="utf-8"))["cubes"][0]


class TestLongShape:
    def test_deal_point_name_is_a_dimension_not_a_measure(self, model: dict) -> None:
        """The extensibility invariant. If a deal point were a measure, MAUD's 93rd would be a
        model edit; as a dimension it is rows and this file never changes."""
        dimensions = {d["name"] for d in model["dimensions"]}
        assert "deal_point_name" in dimensions
        assert not any("fiduciary" in m["name"].lower() for m in model["measures"])

    def test_no_measure_is_named_after_a_specific_deal_point(self, model: dict) -> None:
        loaded_names = {m["name"] for m in model["measures"]}
        assert loaded_names == {
            "n",
            "present_count",
            "count_distinct_matters",
            "expert_labelled_n",
            "with_source_span_n",
            "matters_total",
        }, "measure names are the eval's label space — changing this set is an API change"


class TestNumeratorAndDenominatorAreSeparate:
    def test_both_exist_as_measures(self, model: dict) -> None:
        """So the UI can render "6 of 8". A single pre-divided ratio measure would force 75%,
        which claims precision an n of 8 does not support."""
        measures = {m["name"]: m for m in model["measures"]}
        assert measures["n"]["type"] == "count"
        assert measures["present_count"]["type"] == "count"
        assert measures["present_count"]["filters"]

    def test_no_ratio_measure_exists(self, model: dict) -> None:
        for measure in model["measures"]:
            assert measure["type"] != "number" or "/" not in measure.get("sql", ""), (
                f"{measure['name']} pre-divides; the UI must receive numerator and denominator"
            )


class TestApproximationIsForbidden:
    def test_no_count_distinct_approx_anywhere_in_the_model(self) -> None:
        """HyperLogLog is approximate and this product's claim is defensible numbers."""
        for path in MODEL_DIR.glob("*.yml"):
            # comment lines are excluded: the file's own header tells the next author never to
            # use it, and a comment cannot configure anything
            configured = [
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            ]
            assert "count_distinct_approx" not in "\n".join(configured), path.name

    def test_distinct_counts_are_exact(self, model: dict) -> None:
        distincts = [m for m in model["measures"] if m["type"].startswith("count_distinct")]
        assert distincts
        assert all(m["type"] == "count_distinct" for m in distincts)


class TestTheAgentCanReadThis:
    def test_every_measure_and_dimension_has_a_description(self, model: dict) -> None:
        """The description is what the agent sees in /meta. A measure without one is a measure
        the model has to guess about."""
        public = [d for d in model["dimensions"] if d.get("public") is not False]
        for item in [*model["measures"], *public]:
            assert item.get("description", "").strip(), f"{item['name']} has no description"

    def test_descriptions_say_when_not_to_use_the_measure(self, model: dict) -> None:
        joined = " ".join(m["description"] for m in model["measures"]).lower()
        assert "never" in joined or "do not" in joined

    def test_is_inferred_is_exposed_so_inferred_data_can_be_excluded(self, model: dict) -> None:
        assert "is_inferred" in {d["name"] for d in model["dimensions"]}


class TestRefreshKey:
    def test_refresh_key_is_max_updated_at(self, model: dict) -> None:
        """Paired with the ingest's IS DISTINCT FROM guards (#11): a no-op re-ingest must not
        invalidate every cached aggregate."""
        assert "MAX(updated_at)" in model["refresh_key"]["sql"]


def _cube_up() -> bool:
    try:
        urllib.request.urlopen(f"{CUBE_URL}/meta", timeout=3)
        return True
    except Exception:  # noqa: BLE001 - availability probe
        return False


@pytest.mark.skipif(not _cube_up(), reason="Cube not running")
class TestAgainstLiveCube:
    def _query(self, query: dict) -> list[dict]:
        url = f"{CUBE_URL}/load?query=" + urllib.parse.quote(json.dumps(query))
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)["data"]

    def test_meta_exposes_the_descriptions_the_agent_selects_from(self) -> None:
        with urllib.request.urlopen(f"{CUBE_URL}/meta", timeout=10) as response:
            meta = json.load(response)
        cube = next(c for c in meta["cubes"] if c["name"] == "deal_points")
        n = next(m for m in cube["measures"] if m["name"] == "deal_points.n")
        assert "denominator" in n["description"].lower()

    def test_a_real_rollup_returns_a_distribution_with_its_denominator(self) -> None:
        rows = self._query(
            {
                "measures": ["deal_points.n", "deal_points.present_count"],
                "dimensions": ["deal_points.position"],
                "filters": [
                    {
                        "member": "deal_points.deal_point_name",
                        "operator": "equals",
                        "values": [
                            "Fiduciary exception:  Board determination standard-Answer (no-shop)"
                        ],
                    }
                ],
                "order": {"deal_points.n": "desc"},
            }
        )
        assert rows, "the rollup the whole product exists for returned nothing"
        assert sum(int(r["deal_points.n"]) for r in rows) == 151
        absent = next(r for r in rows if r["deal_points.position"] == "None")
        assert int(absent["deal_points.present_count"]) == 0


MATTERS = MODEL_DIR / "matters.yml"


@pytest.fixture(scope="module")
def matters_model() -> dict:
    return yaml.safe_load(MATTERS.read_text(encoding="utf-8"))


class TestMattersModel:
    def test_folio_levels_are_dimensions(self, matters_model: dict) -> None:
        folio = next(c for c in matters_model["cubes"] if c["name"] == "folio_concepts")
        names = {d["name"] for d in folio["dimensions"]}
        assert {"level_1_code", "level_2_code", "level_3_code", "label"} <= names

    def test_deal_size_band_is_defined_once_in_the_model(self, matters_model: dict) -> None:
        """Two definitions of a band is two answers to the same question, and the one the
        partner reads would be the one in the UI."""
        matters = next(c for c in matters_model["cubes"] if c["name"] == "matters")
        band = next(d for d in matters["dimensions"] if d["name"] == "deal_size_band")
        assert "$200M-1B" in band["sql"]

    def test_frontend_does_not_restate_the_band_thresholds(self) -> None:
        """The AC: the frontend must read bands from the API. A literal in the UI source means
        it has its own definition."""
        src = Path(__file__).resolve().parents[2] / "frontend" / "src"
        offenders = [
            path.name
            for path in src.rglob("*.ts*")
            if any(token in path.read_text(encoding="utf-8") for token in ("$200M", "200000000"))
        ]
        assert offenders == [], f"deal-size bands hardcoded in {offenders}"

    def test_matters_joins_deal_points(self, matters_model: dict) -> None:
        """So a matter-level filter can constrain a deal-point rollup."""
        matters = next(c for c in matters_model["cubes"] if c["name"] == "matters")
        joins = {j["name"]: j for j in matters["joins"]}
        assert joins["deal_points"]["relationship"] == "one_to_many"
        assert joins["folio_concepts"]["relationship"] == "many_to_one"

    def test_hierarchy_finding_is_recorded_with_the_version(self) -> None:
        """The AC asks which approach was used and why — the answer has to survive in the file."""
        header = MATTERS.read_text(encoding="utf-8")[:2000]
        assert "1.7.15" in header
        assert "hierarchies" in header


@pytest.mark.skipif(not _cube_up(), reason="Cube not running")
class TestFacetCountsAgainstSql:
    def test_facet_counts_match_hand_computed_sql(self) -> None:
        """Verified against `SELECT label, count(*) ... GROUP BY 1` run directly on Postgres:
        Health Care 25, Finance 25, Manufacturing 22, Information 18, Real Estate 12."""
        url = f"{CUBE_URL}/load?query=" + urllib.parse.quote(
            json.dumps(
                {
                    "measures": ["comparable_deals.n"],
                    "dimensions": ["comparable_deals.label"],
                    "order": {"comparable_deals.n": "desc"},
                }
            )
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            rows = json.load(response)["data"]
        counts = {r["comparable_deals.label"]: int(r["comparable_deals.n"]) for r in rows}
        assert counts["Health Care Industry"] == 25
        assert counts["Finance and Insurance Services Industry"] == 25
        assert counts["Manufacturing Industry"] == 22
        assert sum(counts.values()) == 152, "every matter must appear in exactly one facet cell"

    def test_unclassified_matters_are_visible_not_dropped(self) -> None:
        """18 matters have no industry. An inner join would hide them; the product must show
        them, or a coverage grid quietly understates what it does not know."""
        url = f"{CUBE_URL}/load?query=" + urllib.parse.quote(
            json.dumps(
                {
                    "measures": ["comparable_deals.n"],
                    "dimensions": ["comparable_deals.has_industry"],
                }
            )
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            rows = json.load(response)["data"]
        # Cube returns JSON booleans here, so normalise rather than assuming a spelling
        by_flag = {
            str(r["comparable_deals.has_industry"]).lower(): int(r["comparable_deals.n"])
            for r in rows
        }
        assert by_flag["false"] == 18
        assert by_flag["true"] == 134

    def test_a_matter_filter_constrains_a_deal_point_rollup(self) -> None:
        """The join's whole purpose: 'fiduciary out, healthcare only' has to be one query."""
        url = f"{CUBE_URL}/load?query=" + urllib.parse.quote(
            json.dumps(
                {
                    "measures": ["deal_points.n"],
                    "dimensions": ["deal_points.position"],
                    "filters": [
                        {
                            "member": "deal_points.deal_point_name",
                            "operator": "equals",
                            "values": [
                                "Fiduciary exception:  Board determination standard-Answer (no-shop)"
                            ],
                        },
                        {
                            "member": "folio_concepts.label",
                            "operator": "equals",
                            "values": ["Health Care Industry"],
                        },
                    ],
                    "order": {"deal_points.n": "desc"},
                }
            )
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            rows = json.load(response)["data"]
        total = sum(int(r["deal_points.n"]) for r in rows)
        assert total == 25, f"healthcare slice should be the 25 health-care matters, got {total}"
