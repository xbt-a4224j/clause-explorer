"""A provider rate limit must read as a rate limit, not as "an internal error occurred".

Hit for real on 2026-09-06 while benchmarking interpretation strategies:

    openai.RateLimitError: Error code: 429 — Rate limit reached for gpt-4o-mini on requests
    per day (RPD): Limit 10000, Used 10000, Requested 1.

The Ask box showed `an internal error occurred`. That is the worst possible message here,
because it is indistinguishable from a bug in the app: a reader retries, gets the same thing,
and concludes the demo is broken. The truthful message — "the provider is rate limited, this
will work again shortly" — costs one exception handler.

Worth knowing the shape of the limit, too. It was **requests per day**, not spend. The whole
night's experimenting cost a few dollars; what ran out was a request count. Cost was never the
constraint, so a cost ceiling would not have prevented this and a request budget would.
"""

from __future__ import annotations

import httpx
import pytest
from explorer.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key must be present or the route short-circuits on "OPENAI_API_KEY is not set"
    before it can reach the provider — a different 503 with a different, correct message."""
    from explorer.api.settings import settings

    monkeypatch.setattr(settings, "openai_api_key", "sk" + "-test-" + "a" * 20)


def _rate_limited() -> Exception:
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request, json={"error": {"message": "RPD exceeded"}})
    return openai.RateLimitError("rate limited", response=response, body=None)


class TestARateLimitIsNotAnInternalError:
    def test_ask_reports_it_as_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import explorer.api.ask as ask_module

        def boom(*_a: object, **_k: object) -> None:
            raise _rate_limited()

        monkeypatch.setattr(ask_module, "interpret", boom)
        response = client.post("/agent/ask", json={"question": "what is market"})
        assert response.status_code == 503, "a provider limit is upstream unavailability"

    def test_the_message_says_rate_limit_and_not_internal_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The reader has to be able to tell "try again in a minute" from "this is broken"."""
        import explorer.api.ask as ask_module

        def boom(*_a: object, **_k: object) -> None:
            raise _rate_limited()

        monkeypatch.setattr(ask_module, "interpret", boom)
        body = client.post("/agent/ask", json={"question": "what is market"}).json()
        message = body["error"]["message"].lower()
        assert "rate limit" in message
        assert "internal error" not in message
