"""Shared fixtures.

`maud_parsed` is session-scoped because parsing the corpus reads 120 MB of CSV and
whitespace-normalizes 53 MB of contract text. Per-class it dominated the test run; once per
session it is a few seconds.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def maud_parsed():
    from explorer.ingest.maud import parse_maud

    return parse_maud()


@pytest.fixture(autouse=True)
def _no_shaped_interpretation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep /agent/ask on its free-form path unless a test opts in.

    Two reasons, and the second is the important one.

    The narrow reason: the shaped path (agent/interpret.py) is two extra model calls in front
    of `select_with_usage`, and the ~20 tests written before it exist stub *that* function.
    They should keep asserting what they were written to assert rather than being rewritten to
    accommodate a path they are not about; the shaped path has its own tests in
    test_interpret_flow.py and test_question_shape.py.

    The real reason: without this the suite makes LIVE API CALLS. `pytest -m "not needs_key"`
    reads as a guarantee that no test spends money or needs a network, and it is not one —
    `settings` loads `.env`, so `env -u OPENAI_API_KEY` clears the variable and pydantic puts
    it straight back from the file. Every `needs_key` mark in this suite is a convention the
    suite cannot enforce. That is worth fixing properly (a fixture that empties the key for the
    whole session, or a transport that refuses outbound calls); this pins the one path that
    newly reached the network.
    """
    import explorer.api.ask as ask_module

    monkeypatch.setattr(ask_module, "interpret", lambda *a, **k: None)
