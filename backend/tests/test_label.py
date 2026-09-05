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


@needs_corpus
class TestQueueDrawsFromTheFullPredictionSet:
    """#44: the queue's reach is the calibration run's reach.

    Before #44 the committed predictions covered 5 hand-picked deal points, so the reviewer's
    queue could only ever surface disagreements on 5% of the label space — the deal points
    least likely to need review, since they were picked for being easy. Nothing in `label.py`
    changes here: the queue reads whatever was committed, which is the point of it having been
    written that way. This test is the assertion that the committed file is now the wide one.
    """

    def test_the_queue_spans_the_whole_committed_prediction_set(self, client: TestClient) -> None:
        from explorer.api.label import PREDICTIONS_FILE

        predictions = json.loads(PREDICTIONS_FILE.read_text())
        body = client.get("/label/queue").json()
        assert body["queue_size"] == len(predictions)
        assert len({i["deal_point_name"] for i in body["items"]}) > 5


class TestDecide:
    def test_accepting_a_label_writes_to_the_labels_table(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        written = []

        class FakeCursor:
            """#56: the endpoint now reads the deal point's vocabulary before it writes, so the
            fake has to answer that read. `Yes` is in the set, so the write still happens and
            this test still asserts what it always did."""

            def fetchall(self) -> list[tuple[str]]:
                return [("Yes",), ("No",)]

        class FakeConn:
            def execute(self, sql: str, params: object = None) -> FakeCursor:
                written.append((sql, params))
                return FakeCursor()

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
        # the vocabulary read comes first, then the insert
        assert "SELECT DISTINCT position" in written[0][0]
        assert "INSERT INTO labels" in written[-1][0]

    def test_a_missing_value_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/label/decide",
            json={"matter_id": "contract_1", "deal_point_name": "Ticking fee"},
        )
        assert response.status_code == 422


# --- the write path has a vocabulary (#56) -------------------------------------------------
#
# `POST /label/decide` took any non-empty string and wrote it into a table that grades the
# extractor. Two of the six rows this shipped with were `s` (the Skip key) and `N` (a half-typed
# `No`), neither of which is a possible answer to its question. A graded table with keystrokes in
# it is worse than an empty one, because the number it produces looks like a measurement.


def test_a_value_outside_the_deal_points_vocabulary_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/label/decide",
        json={
            "matter_id": "contract_10",
            "deal_point_name": "Acquisition Proposal required to be publicly disclosed-Answer (Y/N)",
            "value": "s",
        },
    )
    assert response.status_code == 422
    detail = response.json()["error"]["message"]
    # the rejection has to name what was allowed, or the caller cannot fix it
    assert "Yes" in detail and "No" in detail


def test_a_value_inside_the_vocabulary_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/label/decide",
        json={
            "matter_id": "contract_10",
            "deal_point_name": "Acquisition Proposal required to be publicly disclosed-Answer (Y/N)",
            "value": "No",
        },
    )
    assert response.status_code == 200


def test_an_unknown_deal_point_is_rejected_rather_than_written(client: TestClient) -> None:
    """A deal point with no recorded positions has no vocabulary to check against, so there is
    no safe value to accept for it."""
    response = client.post(
        "/label/decide",
        json={"matter_id": "contract_10", "deal_point_name": "Not A Deal Point", "value": "No"},
    )
    assert response.status_code == 422
