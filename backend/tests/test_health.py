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
