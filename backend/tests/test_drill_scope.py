"""A scoped answer must drill to the scoped matters.

Ask reported "Health Care Industry, 26 agreements took this position", and clicking through
listed ACACIA COMMUNICATIONS — a Cisco acquisition, not a health-care deal. The drill sent only
`{subject, position}`, so it ran corpus-wide, and the platform's own `onDrill(subject, position)`
contract had nowhere to put the scope. The count and the list below it were describing different
sets of agreements, on the tab whose subject is provenance.

Found 2026-09-08 by driving the new one-shot Ask surface, which made an existing defect visible:
the old chip flow had the same hole.

`record_ids` already scopes both the gate count and the text query, so the fix resolves the
question's filters to ids with one Cube call and changes no SQL.
"""

from __future__ import annotations

from typing import Any

import pytest
from explorer.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


class TestScopedDrill:
    def test_filters_are_resolved_to_record_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The scope reaches the queries that fetch and gate the text."""
        seen: dict[str, Any] = {}

        def fake_cube(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
            seen["cube"] = payload
            return [{"comparable_deals.id": "m1"}, {"comparable_deals.id": "m2"}]

        def fake_n(subject: str, record_ids: list[str], position: str) -> int:
            seen["n_ids"] = list(record_ids)
            return 26

        def fake_rows(
            subject: str, record_ids: list[str], position: str | None = None
        ) -> list[tuple[Any, ...]]:
            seen["query_ids"] = list(record_ids)
            return []

        monkeypatch.setattr("explorer.api.deal_terms.cube_query", fake_cube)
        monkeypatch.setattr("explorer.api.deal_terms._position_n", fake_n)
        monkeypatch.setattr("explorer.api.deal_terms._run_drill_query", fake_rows)

        response = client.post(
            "/deal-terms/drill",
            json={
                "subject": "Fiduciary exception: Board determination trigger (no shop)-Answer",
                "position": "Superior Offer",
                "filters": [
                    {
                        "member": "comparable_deals.label",
                        "operator": "equals",
                        "values": ["Health Care Industry"],
                    }
                ],
            },
        )

        assert response.status_code == 200, response.text
        assert seen["cube"]["dimensions"] == ["comparable_deals.id"]
        assert seen["cube"]["filters"][0]["values"] == ["Health Care Industry"]
        assert seen["n_ids"] == ["m1", "m2"], "the gate must count only the scoped matters"
        assert seen["query_ids"] == ["m1", "m2"], "the text query must be scoped too"

    def test_an_unscoped_drill_is_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A question with no scope beyond the deal point still drills corpus-wide, and must
        not pay for a Cube call to discover that."""
        called = {"cube": False}

        def fake_cube(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
            called["cube"] = True
            return []

        monkeypatch.setattr("explorer.api.deal_terms.cube_query", fake_cube)
        monkeypatch.setattr("explorer.api.deal_terms._position_n", lambda s, i, p: 143)
        monkeypatch.setattr("explorer.api.deal_terms._run_drill_query", lambda s, i, p=None: [])

        response = client.post(
            "/deal-terms/drill",
            json={"subject": "Knowledge Definition-Answer", "position": "Actual knowledge"},
        )
        assert response.status_code == 200, response.text
        assert called["cube"] is False
