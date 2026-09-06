#!/usr/bin/env python3
"""How many model requests are left, and when the bucket refills.

The limit that bit on 2026-09-06 was requests-per-DAY (10,000), not spend — a night of
benchmarking cost single-digit dollars and still ran out. It is a rolling window rather than a
midnight reset, so the answer to "can I demo right now" is `remaining`, not the clock.

    python scripts/quota.py
"""

from __future__ import annotations

import datetime
import os
import sys

import httpx


def main() -> int:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY is not set (source .env first)")
        return 1
    # max_tokens=1 on the cheapest model: this costs one request from the bucket it reports on,
    # which is the only way to read the headers.
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "."}],
        },
        timeout=30,
    )
    h = response.headers
    remaining = h.get("x-ratelimit-remaining-requests", "?")
    limit = h.get("x-ratelimit-limit-requests", "?")
    reset = h.get("x-ratelimit-reset-requests", "?")
    now = datetime.datetime.now(datetime.UTC).strftime("%H:%M UTC")
    print(f"  requests  {remaining} of {limit} left · full refill in {reset} · now {now}")
    print(
        f"  tokens    {h.get('x-ratelimit-remaining-tokens', '?')} of "
        f"{h.get('x-ratelimit-limit-tokens', '?')} per minute"
    )
    if remaining.isdigit():
        n = int(remaining)
        cost = "  a demo is ~2 requests per question"
        print(f"  -> {'fine' if n > 200 else 'LOW' if n > 30 else 'EXHAUSTED'}.{cost}")
    return 0 if response.status_code == 200 else 2


if __name__ == "__main__":
    sys.exit(main())
