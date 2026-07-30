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
from typing import ClassVar

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
            "numeric_n",
            "median_numeric_value",
            "p25_numeric_value",
            "p75_numeric_value",
            "mean_numeric_value_do_not_use_for_market",
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


class TestFreshnessContract:
    """#14: "does new data show up automatically?" must have a defined answer."""

    def test_every_cube_declares_an_explicit_refresh_key(self) -> None:
        for path in MODEL_DIR.glob("*.yml"):
            model = yaml.safe_load(path.read_text(encoding="utf-8"))
            for cube in model.get("cubes", []):
                sql = cube.get("refresh_key", {}).get("sql", "")
                assert "MAX(updated_at)" in sql, f"{cube['name']} relies on the default"

    def test_no_pre_aggregations_anywhere(self) -> None:
        """Not an oversight — a deliberate decision recorded in the model header. At 152
        matters a pre-aggregation buys nothing and adds a second place to be wrong."""
        for path in MODEL_DIR.glob("*.yml"):
            configured = [
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            ]
            assert "pre_aggregations" not in "\n".join(configured), path.name

    def test_the_measured_staleness_window_is_recorded(self) -> None:
        header = MATTERS.read_text(encoding="utf-8")[:4000]
        assert "11.3s" in header and "without a restart" in header


@pytest.mark.skipif(not _cube_up(), reason="Cube not running")
class TestNewRowsAppearWithoutARestart:
    """#14's live test: data inserted into Postgres is visible through Cube with nothing
    restarted.

    Asserted with a **query Cube has never run before** (filtered to the probe row) rather than
    by polling a cached aggregate. The aggregate version measured the real staleness window —
    11.3s, recorded in the model headers — but as a test it was timing-dependent on Cube's
    result cache and flaked under full-suite load. The property that matters is "no restart
    required", and this proves it deterministically; the window itself is a documented
    measurement, not an assertion.
    """

    def test_an_inserted_row_is_visible_through_cube_without_a_restart(self) -> None:
        import time
        import uuid

        import psycopg

        dsn = os.getenv(
            "CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer"
        )
        # unique per run: a fixed id means Cube can still be serving a cached view of the
        # *previous* run's probe (inserted and deleted seconds ago), which made the pre-check
        # fail rather than the behaviour under test
        probe = f"refresh_probe_{uuid.uuid4().hex[:12]}"

        def probe_rows() -> list[dict]:
            """[] while Cube is warming or the row is not visible yet."""
            url = f"{CUBE_URL}/load?query=" + urllib.parse.quote(
                json.dumps(
                    {
                        "measures": ["matters.n"],
                        "dimensions": ["matters.target_name"],
                        "filters": [
                            {"member": "matters.id", "operator": "equals", "values": [probe]}
                        ],
                    }
                )
            )
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    return list(json.load(response)["data"])
            except (urllib.error.URLError, KeyError):
                return []

        assert probe_rows() == [], "a fresh id cannot already be in the corpus"

        with psycopg.connect(dsn) as conn:
            conn.execute(
                "INSERT INTO matters (id, source_file, source_contract_title, corpus, "
                "target_name) VALUES (%s, 'probe', 'refresh_key probe (#14)', 'maud', "
                "'REFRESH PROBE INC.')",
                (probe,),
            )
            conn.commit()
        try:
            # The staleness window applies even to a query Cube has never run before — tested:
            # a fresh, filtered query returns [] immediately after the INSERT. So it is the
            # refresh-key *value* that is cached for ~10s, not the query result. Hence polling.
            # The deadline is 120s rather than the measured ~11s purely to absorb full-suite
            # load; the assertion is unchanged.
            deadline = time.time() + 120
            rows: list[dict] = []
            while time.time() < deadline:
                rows = probe_rows()
                if rows:
                    break
                time.sleep(2)
            assert rows, "inserted row never appeared — a restart should not be needed"
            assert rows[0]["matters.target_name"] == "REFRESH PROBE INC."
        finally:
            with psycopg.connect(dsn) as conn:
                conn.execute("DELETE FROM matters WHERE id = %s", (probe,))
                conn.commit()


class TestPercentilesNotAverages:
    """#15. `type: avg` where a median is meant is the most dangerous measure that could sit in
    this model: right magnitude, right units, wrong statistic, and nothing about the output
    looks wrong."""

    def test_medians_use_percentile_cont(self, model: dict) -> None:
        measures = {m["name"]: m for m in model["measures"]}
        for name, fraction in (
            ("median_numeric_value", "0.5"),
            ("p25_numeric_value", "0.25"),
            ("p75_numeric_value", "0.75"),
        ):
            sql = measures[name]["sql"]
            assert f"PERCENTILE_CONT({fraction})" in sql
            assert "WITHIN GROUP (ORDER BY" in sql

    def test_the_only_avg_is_named_so_it_cannot_be_used_by_accident(self, model: dict) -> None:
        averages = [m for m in model["measures"] if m["type"] == "avg"]
        assert [m["name"] for m in averages] == ["mean_numeric_value_do_not_use_for_market"]
        assert "DO NOT use this" in averages[0]["description"]

    def test_every_percentile_explains_why_avg_is_wrong(self, model: dict) -> None:
        for name in ("median_numeric_value", "p25_numeric_value", "p75_numeric_value"):
            measure = next(m for m in model["measures"] if m["name"] == name)
            text = measure["description"].lower()
            assert "never an average" in text or "same caveats" in text or "median alone" in text

    def test_percentiles_have_their_own_denominator(self, model: dict) -> None:
        """809 of 12,937 rows carry a number, so the percentile's n is not the deal point's n."""
        numeric_n = next(m for m in model["measures"] if m["name"] == "numeric_n")
        assert "DENOMINATOR FOR EVERY PERCENTILE" in numeric_n["description"]


class TestMedianOnASkewedFixture:
    """A hand-computed check that median and mean genuinely differ, so the model's choice is
    demonstrated rather than asserted. Postgres does the arithmetic — the same
    percentile_cont the Cube measure emits."""

    # one long outlier, as real deal data has
    SKEWED: ClassVar[list[int]] = [2, 2, 2, 2, 2, 3, 3, 4, 40]

    def test_median_is_not_the_mean(self) -> None:
        import statistics

        assert statistics.median(self.SKEWED) == 2
        assert round(statistics.mean(self.SKEWED), 2) == 6.67
        assert statistics.median(self.SKEWED) != statistics.mean(self.SKEWED)

    @pytest.mark.skipif(not _cube_up(), reason="Postgres/Cube stack not running")
    def test_postgres_percentile_cont_matches_the_hand_computed_median(self) -> None:
        import psycopg

        dsn = os.getenv(
            "CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer"
        )
        with psycopg.connect(dsn) as conn:
            row = conn.execute(
                "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY v), avg(v) "
                "FROM unnest(%s::numeric[]) AS t(v)",
                (self.SKEWED,),
            ).fetchone()
        median, mean = float(row[0]), float(row[1])
        assert median == 2.0
        assert round(mean, 2) == 6.67
        assert median != mean, "if these ever match, the fixture stopped being skewed"


@pytest.mark.skipif(not _cube_up(), reason="Cube not running")
class TestPercentilesAgainstLiveCube:
    def test_median_and_mean_diverge_on_the_real_corpus(self) -> None:
        """The measured divergence that justifies the whole issue."""
        url = f"{CUBE_URL}/load?query=" + urllib.parse.quote(
            json.dumps(
                {
                    "measures": [
                        "deal_points.numeric_n",
                        "deal_points.median_numeric_value",
                        "deal_points.mean_numeric_value_do_not_use_for_market",
                    ],
                    "filters": [
                        {
                            "member": "deal_points.deal_point_name",
                            "operator": "equals",
                            "values": [
                                "Additional matching rights period for modifications (COR)-Answer"
                            ],
                        }
                    ],
                }
            )
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            row = json.load(response)["data"][0]
        assert int(row["deal_points.numeric_n"]) == 143
        assert float(row["deal_points.median_numeric_value"]) == 2.0
        assert round(float(row["deal_points.mean_numeric_value_do_not_use_for_market"]), 2) == 2.54
