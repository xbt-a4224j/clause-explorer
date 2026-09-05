"""Chip corrections on Ask, recorded as selection-eval cases (#51).

When someone edits a chip before running, that is a **labelled disagreement**: here is what
the model selected, here is what a person said it should have selected. The measure-selection
eval has 25 authored cases written in July; every real correction is a case it lacks.

Agreements are recorded too. An eval that only learns from corrections learns only what the
model got wrong, and "the model was right and nobody touched it" is the other half of an
accuracy figure.

**Only a human writes here.** The route is reached from the confirm click and from nowhere
else; `/agent/ask` never touches this table, and a test asserts that. A model writing its own
eval data would make the corrections row an opinion the model already held rather than
evidence against it.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.api.main import app
from explorer.api.selection_corrections import changed_fields
from explorer.evals.measure_selection import grade_corrections
from fastapi.testclient import TestClient

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

MODEL_SELECTION = {
    "measures": ["comparable_deals.n"],
    "dimensions": [],
    "filters": [
        {"member": "comparable_deals.label", "operator": "equals", "values": ["Healthcare"]}
    ],
}


def _db_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            conn.execute("SELECT 1 FROM selection_corrections LIMIT 1")
        return True
    except Exception:  # noqa: BLE001 - availability probe; the table may not be migrated yet
        return False


needs_db = pytest.mark.skipif(not _db_ready(), reason="selection_corrections not migrated")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def clean_rows():  # type: ignore[no-untyped-def]
    """Deletes only this test's own rows, by labeller. The table is shared with whatever a
    human has actually recorded through the UI, and a blanket DELETE would throw that away."""
    marker = "pytest-51"
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM selection_corrections WHERE labeller = %s", (marker,))
    yield marker
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM selection_corrections WHERE labeller = %s", (marker,))


def _rows(marker: str) -> list[tuple]:
    with psycopg.connect(DSN) as conn:
        return conn.execute(
            "SELECT question, model_selection, confirmed_selection, changed_fields, agreed "
            "FROM selection_corrections WHERE labeller = %s ORDER BY id",
            (marker,),
        ).fetchall()


class TestWhichFieldsChanged:
    """Pure, so the naming of a change is testable without a database."""

    def test_an_edited_filter_value_names_the_filter_field(self) -> None:
        confirmed = {
            "measures": ["comparable_deals.n"],
            "dimensions": [],
            "filters": [
                {
                    "member": "comparable_deals.label",
                    "operator": "equals",
                    "values": ["Health Care Industry"],
                }
            ],
        }
        assert changed_fields(MODEL_SELECTION, confirmed) == ["filters"]

    def test_an_identical_selection_changed_nothing(self) -> None:
        assert changed_fields(MODEL_SELECTION, dict(MODEL_SELECTION)) == []

    def test_each_part_is_named_separately_rather_than_as_one_diff_flag(self) -> None:
        confirmed = {
            "measures": ["deal_points.n"],
            "dimensions": ["deal_points.position"],
            "filters": [],
        }
        assert changed_fields(MODEL_SELECTION, confirmed) == ["measures", "dimensions", "filters"]

    def test_order_is_not_a_change(self) -> None:
        """A selection is a set of names. Re-ordering it is not a disagreement, and counting
        it as one would inflate the correction rate with noise."""
        model = {"measures": ["a", "b"], "dimensions": [], "filters": []}
        confirmed = {"measures": ["b", "a"], "dimensions": [], "filters": []}
        assert changed_fields(model, confirmed) == []


@needs_db
class TestACorrectionIsRecorded:
    def test_a_corrected_filter_value_writes_one_row_naming_the_changed_field(
        self, client: TestClient, clean_rows: str
    ) -> None:
        response = client.post(
            "/agent/selection-correction",
            json={
                "question": "healthcare deals",
                "model_selection": MODEL_SELECTION,
                "confirmed_selection": {
                    "measures": ["comparable_deals.n"],
                    "dimensions": [],
                    "filters": [
                        {
                            "member": "comparable_deals.label",
                            "operator": "equals",
                            "values": ["Health Care Industry"],
                        }
                    ],
                },
                "labeller": clean_rows,
            },
        )
        assert response.status_code == 200
        assert response.json()["agreed"] is False
        assert response.json()["changed_fields"] == ["filters"]

        rows = _rows(clean_rows)
        assert len(rows) == 1
        question, model, confirmed, changed, agreed = rows[0]
        assert question == "healthcare deals"
        assert changed == ["filters"]
        assert agreed is False
        assert model["filters"][0]["values"] == ["Healthcare"]
        assert confirmed["filters"][0]["values"] == ["Health Care Industry"]

    def test_an_unchanged_selection_is_recorded_as_an_agreement(
        self, client: TestClient, clean_rows: str
    ) -> None:
        """The eval learns what the model got right as well as wrong."""
        response = client.post(
            "/agent/selection-correction",
            json={
                "question": "healthcare deals",
                "model_selection": MODEL_SELECTION,
                "confirmed_selection": MODEL_SELECTION,
                "labeller": clean_rows,
            },
        )
        assert response.json()["agreed"] is True
        rows = _rows(clean_rows)
        assert len(rows) == 1
        assert rows[0][4] is True
        assert rows[0][3] == []


@needs_db
class TestOnlyAHumanWrites:
    def test_asking_a_question_records_nothing(
        self, client: TestClient, clean_rows: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`/agent/ask` is the model's half of the loop. If it wrote here, the corrections
        table would hold the model's own opinion rather than evidence against it."""
        from explorer.agent.select import Vocabulary
        from explorer.api import ask as ask_module

        vocabulary = Vocabulary(measures=("deal_points.n",), dimensions=())
        monkeypatch.setattr(ask_module, "fetch_vocabulary", lambda: vocabulary)
        monkeypatch.setattr(
            ask_module,
            "select_with_usage",
            lambda q, v, k: ask_module.SelectionCall(
                selection={
                    "measures": ["deal_points.n"],
                    "dimensions": [],
                    "filters": [],
                    "timeDimensions": [],
                },
                model="gpt-4o-mini",
                prompt_tokens=10,
                completion_tokens=2,
                latency_ms=1.0,
            ),
        )
        monkeypatch.setattr(ask_module.settings, "openai_api_key", "test-key-not-real")

        before = len(_rows(clean_rows))
        client.post("/agent/ask", json={"question": "how many"})
        assert len(_rows(clean_rows)) == before


class TestGradingReportsBothSetsSeparately:
    """Authored and corrections never fold into one headline. They measure different things:
    25 questions someone wrote to probe the vocabulary, versus whatever real users happened to
    ask, which is not a balanced sample of anything."""

    def test_the_harness_grades_a_corrections_set_alongside_the_authored_one(self) -> None:
        summary = grade_corrections(
            [
                {"agreed": True, "changed_fields": []},
                {"agreed": False, "changed_fields": ["filters"]},
                {"agreed": False, "changed_fields": ["measures"]},
                {"agreed": True, "changed_fields": []},
            ]
        )
        assert summary["corrections_count"] == 4
        assert summary["corrections_agreed"] == 2
        assert summary["corrections_accuracy"] == 0.5
        # which part of a selection people actually correct is the useful finding
        assert summary["changed_field_counts"] == {"filters": 1, "measures": 1}

    def test_no_corrections_reports_zero_cases_rather_than_zero_accuracy(self) -> None:
        """0.0 accuracy on an empty set reads as "the model is always wrong". n=0 is the
        honest statement, and the panel renders it as "not measured"."""
        summary = grade_corrections([])
        assert summary["corrections_count"] == 0
        assert summary["corrections_accuracy"] is None

    def test_the_authored_run_still_needs_no_database(self) -> None:
        """The authored half stays pure: two committed files in, scores out."""
        from explorer.evals.measure_selection import run

        summary = run()
        assert summary["case_count"] == 25
        assert summary["measure_precision"] == 0.8
