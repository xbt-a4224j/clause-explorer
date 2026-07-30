"""Error envelope contract.

Every non-2xx response has the same shape, so the frontend has exactly one error path to
handle rather than guessing between FastAPI's default `detail` string, a validation array,
and whatever an unhandled exception produces.

Shape: {"error": {"code", "message", "detail"}}
"""

from __future__ import annotations

import pytest
from explorer.api.main import app
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel


class _Body(BaseModel):
    """Module-level so pydantic can resolve the annotation.

    Defining it inside the test fails under `from __future__ import annotations`: the
    annotation is a string and the local name is not in scope when pydantic resolves it.
    """

    n: int


@app.post("/_validate")
def _validate(body: _Body) -> dict:
    return {"n": body.n}


@pytest.fixture(scope="module")
def client() -> TestClient:
    # raise_server_exceptions=False so the 500 handler runs instead of the exception
    # propagating into the test, which is what a real client would see.
    return TestClient(app, raise_server_exceptions=False)


def _envelope(body: dict) -> dict:
    assert "error" in body, f"not an error envelope: {body}"
    err = body["error"]
    assert {"code", "message"} <= set(err)
    return err


class TestEnvelope:
    def test_404_uses_the_envelope(self, client: TestClient) -> None:
        resp = client.get("/no-such-route")
        assert resp.status_code == 404
        assert _envelope(resp.json())["code"] == "not_found"

    def test_unhandled_exception_returns_500_in_the_envelope(self, client: TestClient) -> None:
        @app.get("/_boom")
        def _boom() -> None:
            raise RuntimeError("intentional")

        resp = client.get("/_boom")
        assert resp.status_code == 500
        assert _envelope(resp.json())["code"] == "internal_error"

    def test_internal_error_does_not_leak_the_exception_text(self, client: TestClient) -> None:
        """A traceback can carry a DSN or a key. The client gets a generic message."""
        resp = client.get("/_boom")
        assert "intentional" not in resp.text

    def test_http_exception_message_is_preserved(self, client: TestClient) -> None:
        @app.get("/_teapot")
        def _teapot() -> None:
            raise HTTPException(status_code=418, detail="short and stout")

        err = _envelope(client.get("/_teapot").json())
        assert err["message"] == "short and stout"

    def test_validation_error_uses_the_envelope(self, client: TestClient) -> None:
        resp = client.post("/_validate", json={"n": "not-an-int"})
        assert resp.status_code == 422
        err = _envelope(resp.json())
        assert err["code"] == "validation_error"
        assert err["detail"], "validation failures must say which field"

    def test_every_error_carries_the_request_id(self, client: TestClient) -> None:
        resp = client.get("/no-such-route")
        assert resp.headers.get("x-request-id")


class TestOpenAPI:
    def test_openapi_is_served(self, client: TestClient) -> None:
        assert client.get("/openapi.json").status_code == 200

    def test_healthz_declares_a_response_model(self, client: TestClient) -> None:
        """Routes returning bare dicts produce a useless schema for the frontend."""
        spec = client.get("/openapi.json").json()
        content = spec["paths"]["/healthz"]["get"]["responses"]["200"]["content"]
        assert content["application/json"]["schema"], "/healthz has no response schema"
