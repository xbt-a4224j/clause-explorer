"""`GET /agent/grading` (#36) — the offline grade, served.

The claim this endpoint exists to support is narrow and checkable: because the model's output
is a selection from a fixed vocabulary rather than freeform SQL, correctness is discrete and
can be scored **with no database and no model in the loop**. The grading therefore reads two
committed fixtures and nothing else, and a test asserts exactly that by forbidding a DB
connection during the call.
"""

from __future__ import annotations

import pytest
from explorer.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


class TestGradingIsOffline:
    def test_it_grades_without_a_database_or_a_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def forbidden(*args: object, **kwargs: object) -> None:
            raise AssertionError("grading touched the database — it must be fixture-only")

        monkeypatch.setattr("psycopg.connect", forbidden)
        assert client.get("/agent/grading").status_code == 200

    def test_it_needs_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert client.get("/agent/grading").status_code == 200


class TestTheGrade:
    def test_every_case_is_graded_pass_or_fail(self) -> None:
        body = client.get("/agent/grading").json()
        assert body["cases"]
        assert all(isinstance(c["correct"], bool) for c in body["cases"])

    def test_a_case_shows_expected_beside_actual(self) -> None:
        """A bare pass/fail is not reviewable — the value of a discrete label space is that you
        can see *which* wrong name was chosen."""
        body = client.get("/agent/grading").json()
        case = body["cases"][0]
        assert "expected_measures" in case
        assert "actual_measures" in case

    def test_refusal_cases_are_counted_separately(self) -> None:
        """Refusal accuracy is the worst number in this eval (1 of 5). Averaging it into an
        overall score would bury the one finding a reviewer should hear first."""
        body = client.get("/agent/grading").json()
        assert body["refusal_total"] == 5
        assert body["refusal_correct"] <= body["refusal_total"]

    def test_the_summary_matches_the_cases(self) -> None:
        body = client.get("/agent/grading").json()
        graded = [c for c in body["cases"] if not c["should_refuse"]]
        assert body["answerable_total"] == len(graded)
