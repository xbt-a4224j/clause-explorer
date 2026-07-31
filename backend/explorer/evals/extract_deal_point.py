"""A minimal extractor: predict a deal point's position from raw contract text (#28).

This is deliberately not the product's extraction pipeline — there is none; MAUD's own labels
ARE the product data (CLAUDE.md), and this module exists solely to produce a defensible
calibration figure for a *hypothetical* future extractor, which is exactly what #28 asks for:
"the generalization claim is only credible with a measured accuracy on held-out documents."

The model is constrained to the deal point's own observed position vocabulary (enum) so an
invalid answer is undecidable, mirroring #24's approach to measure selection. It is also asked
to quote the exact supporting text; that quote is located in the contract with a plain
substring search rather than trusted as an offset, so the span is verified the same way every
other drill-through in this app treats provenance — traceable to a byte range, or absent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from explorer.api.logging import get_logger

log = get_logger()

# Contracts run 500KB+; sending one whole is neither affordable nor necessary for the y/n-style
# points calibrated here, which are answered by defined-terms and boilerplate covenants that
# are disproportionately front-loaded in a merger agreement. This is a real methodological
# limitation, stated plainly rather than hidden: a deal point whose answer lives past this
# window is not being fairly evaluated. See docs/results/calibration.md.
CONTEXT_CHARS = 12000


@dataclass(frozen=True)
class Prediction:
    matter_id: str
    deal_point_name: str
    predicted_position: str
    quoted_text: str | None
    span_start: int | None
    span_end: int | None
    tokens: int


def _locate(contract_text: str, quote: str) -> tuple[int | None, int | None]:
    if not quote:
        return None, None
    idx = contract_text.find(quote)
    if idx == -1:
        return None, None
    return idx, idx + len(quote)


def predict(
    matter_id: str,
    contract_text: str,
    deal_point_name: str,
    allowed_positions: list[str],
    api_key: str,
) -> Prediction:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    context = contract_text[:CONTEXT_CHARS]

    schema = {
        "type": "object",
        "properties": {
            "position": {"type": "string", "enum": allowed_positions},
            "quote": {
                "type": "string",
                "description": "The exact supporting sentence, copied verbatim from the "
                "contract. Empty string if the answer is inferred from absence.",
            },
        },
        "required": ["position", "quote"],
        "additionalProperties": False,
    }

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are labelling a merger agreement for the ABA-style deal point "
                    f'"{deal_point_name}". Choose exactly one position from the allowed set '
                    "and quote the exact sentence that supports it, copied verbatim."
                ),
            },
            {"role": "user", "content": context},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "deal_point_prediction", "schema": schema, "strict": True},
        },
    )
    content = json.loads(response.choices[0].message.content or "{}")
    tokens = response.usage.total_tokens if response.usage else 0

    start, end = _locate(context, content.get("quote", ""))
    log.info(
        "calibration_prediction",
        matter_id=matter_id,
        deal_point_name=deal_point_name,
        predicted=content.get("position"),
        tokens=tokens,
        located=start is not None,
    )
    return Prediction(
        matter_id=matter_id,
        deal_point_name=deal_point_name,
        predicted_position=content.get("position", ""),
        quoted_text=content.get("quote") or None,
        span_start=start,
        span_end=end,
        tokens=tokens,
    )
