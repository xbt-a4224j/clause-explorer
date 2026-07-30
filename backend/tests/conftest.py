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
