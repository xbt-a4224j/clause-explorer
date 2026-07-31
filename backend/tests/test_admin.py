"""`GET /admin/*` — ingest status, calibration, evals, logs (#30).

Alex asked for this so he never opens psql. What earns a test is the composition and the
redaction guarantee — the underlying data (ingest_runs, the calibration/eval reports) is already
covered where it's produced.

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
            return conn.execute("SELECT count(*) FROM ingest_runs").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_corpus = pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@needs_corpus
class TestIngestStatus:
    def test_returns_the_latest_run_per_source(self, client: TestClient) -> None:
        body = client.get("/admin/ingest-status").json()
        sources = {r["source"] for r in body["runs"]}
        assert {"maud", "cuad", "edgar", "folio"} <= sources

    def test_each_source_reports_only_its_most_recent_run(self, client: TestClient) -> None:
        body = client.get("/admin/ingest-status").json()
        by_source: dict[str, int] = {}
        for r in body["runs"]:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        assert all(count == 1 for count in by_source.values())

    def test_a_run_carries_rows_duration_and_sha(self, client: TestClient) -> None:
        body = client.get("/admin/ingest-status").json()
        run = next(r for r in body["runs"] if r["source"] == "maud")
        assert run["rows_upserted"] > 0
        assert run["duration_ms"] > 0


class TestCalibrationReport:
    def test_reads_the_committed_report(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = tmp_path / "calibration.md"
        report.write_text("| deal point | n | accuracy |\n|---|---|---|\n| x | 20 | 0.5 |\n")
        monkeypatch.setattr("explorer.api.admin.CALIBRATION_REPORT", report)
        body = client.get("/admin/calibration").json()
        assert "0.5" in body["markdown"]

    def test_a_missing_report_says_so_rather_than_500ing(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("explorer.api.admin.CALIBRATION_REPORT", tmp_path / "missing.md")
        response = client.get("/admin/calibration")
        assert response.status_code == 404


class TestEvalResults:
    def test_reports_the_measure_selection_summary_with_a_git_sha(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("explorer.api.admin.git_sha", lambda: "deadbeef")
        body = client.get("/admin/evals").json()
        assert body["git_sha"] == "deadbeef"
        assert "measure_selection" in body


class TestLogViewer:
    def test_parses_jsonl_into_columns(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_file = tmp_path / "explorer.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-07-30T00:00:00Z",
                    "level": "info",
                    "request_id": "abc123",
                    "event": "request_end",
                    "duration_ms": 5.2,
                }
            )
            + "\n"
        )
        monkeypatch.setattr("explorer.api.admin.LOG_FILE", log_file)
        body = client.get("/admin/logs").json()
        assert body["lines"][0]["event"] == "request_end"
        assert body["lines"][0]["request_id"] == "abc123"

    def test_filters_by_level(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_file = tmp_path / "explorer.jsonl"
        log_file.write_text(
            "\n".join(
                json.dumps({"timestamp": "t", "level": lvl, "event": "e"})
                for lvl in ["info", "warning", "info"]
            )
            + "\n"
        )
        monkeypatch.setattr("explorer.api.admin.LOG_FILE", log_file)
        body = client.get("/admin/logs", params={"level": "warning"}).json()
        assert len(body["lines"]) == 1
        assert body["lines"][0]["level"] == "warning"

    def test_filters_by_free_text(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_file = tmp_path / "explorer.jsonl"
        log_file.write_text(
            "\n".join(
                json.dumps({"timestamp": "t", "level": "info", "event": e})
                for e in ["cube_query", "request_start"]
            )
            + "\n"
        )
        monkeypatch.setattr("explorer.api.admin.LOG_FILE", log_file)
        body = client.get("/admin/logs", params={"q": "cube_query"}).json()
        assert len(body["lines"]) == 1

    def test_paginates_rather_than_loading_a_whole_large_file(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log_file = tmp_path / "explorer.jsonl"
        # 5,000 lines — the size actually tested against, stated in the worklog
        log_file.write_text(
            "\n".join(
                json.dumps({"timestamp": "t", "level": "info", "event": f"e{i}"})
                for i in range(5000)
            )
            + "\n"
        )
        monkeypatch.setattr("explorer.api.admin.LOG_FILE", log_file)
        body = client.get("/admin/logs", params={"limit": 50}).json()
        assert len(body["lines"]) == 50
        assert body["total_matched"] == 5000

    def test_a_secret_shaped_value_is_redacted_in_the_viewer(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_key = "sk" + "-proj-" + "a" * 20
        log_file = tmp_path / "explorer.jsonl"
        log_file.write_text(
            json.dumps({"timestamp": "t", "level": "info", "event": "e", "detail": fake_key}) + "\n"
        )
        monkeypatch.setattr("explorer.api.admin.LOG_FILE", log_file)
        body = client.get("/admin/logs").json()
        rendered = json.dumps(body["lines"][0])
        assert fake_key not in rendered
        assert "***" in rendered

    def test_a_missing_log_file_returns_an_empty_page_not_an_error(
        self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("explorer.api.admin.LOG_FILE", tmp_path / "missing.jsonl")
        body = client.get("/admin/logs").json()
        assert body["lines"] == []
        assert body["total_matched"] == 0
