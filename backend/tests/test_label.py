"""`GET /label/queue`, `POST /label/decide` (#29).

The queue is built from #28's already-committed calibration predictions — real LLM output, no
new API call to serve it — scored against a cheap keyword-count baseline (no key, no
calibration needed) purely by whether the two disagree. Disagreement needs no calibrated
confidence, which is the whole point: it is the cheapest useful signal available before #28's
numbers exist for a given deal point.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import json
import os

import psycopg
import pytest
from explorer.api.main import app
from fastapi.testclient import TestClient

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM matters").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_corpus = pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def predictions_file(tmp_path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    preds = [
        {
            "matter_id": "contract_1",
            "deal_point_name": "Announcement, pendency or consummation of deal (Y/N)",
            "predicted_position": "Yes",
            "quoted_text": "the Merger shall be announced",
            "span_start": 10,
            "span_end": 40,
            "tokens": 900,
        },
        {
            "matter_id": "contract_2",
            "deal_point_name": "Announcement, pendency or consummation of deal (Y/N)",
            "predicted_position": "No",
            "quoted_text": None,
            "span_start": None,
            "span_end": None,
            "tokens": 850,
        },
    ]
    path = tmp_path / "calibration_predictions.json"
    path.write_text(json.dumps(preds))
    monkeypatch.setattr("explorer.api.label.PREDICTIONS_FILE", path)
    return path


@needs_corpus
class TestQueueOrdering:
    def test_disagreeing_items_rank_before_agreeing_ones(
        self, client: TestClient, predictions_file
    ) -> None:  # type: ignore[no-untyped-def]
        body = client.get("/label/queue").json()
        items = body["items"]
        assert items, "queue must not be empty against a real committed corpus"
        disagree_positions = [i for i, item in enumerate(items) if item["disagreement"]]
        agree_positions = [i for i, item in enumerate(items) if not item["disagreement"]]
        if disagree_positions and agree_positions:
            assert max(disagree_positions) < min(agree_positions)

    def test_each_item_carries_both_predictions_and_the_span(
        self, client: TestClient, predictions_file
    ) -> None:  # type: ignore[no-untyped-def]
        body = client.get("/label/queue").json()
        item = body["items"][0]
        assert "llm_prediction" in item
        assert "deterministic_prediction" in item
        assert "matter_id" in item
        assert "deal_point_name" in item

    def test_the_progress_counters_are_reported(self, client: TestClient, predictions_file) -> None:  # type: ignore[no-untyped-def]
        body = client.get("/label/queue").json()
        assert body["queue_size"] == len(body["items"])
        assert "labelled_count" in body


class TestDecide:
    def test_accepting_a_label_writes_to_the_labels_table(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        written = []

        class FakeConn:
            def execute(self, sql: str, params: dict) -> None:  # type: ignore[type-arg]
                written.append((sql, params))

            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *a):  # type: ignore[no-untyped-def]
                return False

        monkeypatch.setattr("explorer.api.label.psycopg.connect", lambda *a, **kw: FakeConn())
        response = client.post(
            "/label/decide",
            json={
                "matter_id": "contract_1",
                "deal_point_name": "Ticking fee",
                "value": "Yes",
                "prior_prediction": "No",
            },
        )
        assert response.status_code == 200
        assert written
        assert "INSERT INTO labels" in written[0][0]

    def test_a_missing_value_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/label/decide",
            json={"matter_id": "contract_1", "deal_point_name": "Ticking fee"},
        )
        assert response.status_code == 422
