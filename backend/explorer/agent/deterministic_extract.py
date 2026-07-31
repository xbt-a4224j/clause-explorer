"""A cheap, keyword-count baseline extractor — the second half of the disagreement pair (#29).

Disagreement mining needs no calibrated confidence to be useful: two independently-built
extractors that land on different answers is itself the signal, and it is cheaper than a
probability nobody has measured yet (#28's calibration work is exactly how that gets measured,
later, for the LLM side). This one calls no API and costs nothing per prediction — a raw keyword
count against the deal point's own name, present/absent in the contract text.

It exists to disagree usefully with the LLM extractor, not to be accurate on its own.
"""

from __future__ import annotations

import re

_STOPWORDS = {"answer", "y", "n", "the", "a", "an", "of", "to", "is", "and", "or", "for"}


def _keywords(deal_point_name: str) -> list[str]:
    words = re.findall(r"[a-z]+", deal_point_name.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def predict_deterministic(
    contract_text: str, deal_point_name: str, allowed_positions: list[str]
) -> str:
    """ "Yes"/"No"-shaped positions only: predicts the affirmative position if any keyword from
    the deal point's own name appears in the text, else the negative one. Falls back to the
    first allowed position if the vocabulary doesn't look like a Yes/No pair."""
    keywords = _keywords(deal_point_name)
    text_lower = contract_text.lower()
    hit = any(k in text_lower for k in keywords)

    positive = next((p for p in allowed_positions if p.strip().lower() == "yes"), None)
    negative = next((p for p in allowed_positions if p.strip().lower() == "no"), None)
    if positive and negative:
        return positive if hit else negative
    return allowed_positions[0] if allowed_positions else ""
