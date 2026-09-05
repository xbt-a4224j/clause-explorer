"""Health endpoint contract.

/healthz reports on each dependency independently. A single boolean would hide which
one is down, which is the only thing the endpoint is useful for.

No API key required — this must pass in CI with OPENAI_API_KEY unset.
"""

from __future__ import annotations

from explorer.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_healthz_returns_200() -> None:
    assert client.get("/healthz").status_code == 200


def test_healthz_reports_each_dependency_separately() -> None:
    body = client.get("/healthz").json()
    assert set(body) >= {"status", "db", "cube", "version"}
    # each dependency reports its own state, not a rolled-up boolean
    assert body["db"] in {"ok", "unreachable"}
    assert body["cube"] in {"ok", "unreachable"}


def test_healthz_status_is_degraded_when_a_dependency_is_down() -> None:
    """The endpoint must not claim ok while a dependency is unreachable."""
    body = client.get("/healthz").json()
    deps_ok = body["db"] == "ok" and body["cube"] == "ok"
    assert body["status"] == ("ok" if deps_ok else "degraded")


def test_root_serves_the_app_shell() -> None:
    resp = client.get("/")
    assert resp.status_code == 200


def test_no_route_outlives_the_surface_that_called_it() -> None:
    """#48 cut the Coverage tab and the Tables tab from the UI.

    `/coverage` had exactly one caller, the Coverage view, so the route goes with it.
    `/tables/{table}/export.csv` had exactly one caller, `Tables.tsx:102`, so it goes too —
    the rest of `/tables/*` stays, because Admin reads ingest status and the Overview corpus
    strip reads its counts through that path. Asserted against the app's own route table so
    it holds with no database.
    """
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any(p == "/coverage" or p.startswith("/coverage/") for p in paths)
    assert not any(p.endswith("export.csv") for p in paths)
    assert "/tables/{table}/rows" in paths
