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
from functools import lru_cache
from typing import Any

from explorer.api.logging import get_logger
from explorer.evals.pricing import cost_usd

log = get_logger()

# Contracts run 500KB+; sending one whole is neither affordable nor necessary for the y/n-style
# points calibrated here, which are answered by defined-terms and boilerplate covenants that
# are disproportionately front-loaded in a merger agreement. This is a real methodological
# limitation, stated plainly rather than hidden: a deal point whose answer lives past this
# window is not being fairly evaluated. See docs/results/calibration.md.
CONTEXT_CHARS = 12000


MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class Prediction:
    matter_id: str
    deal_point_name: str
    predicted_position: str
    quoted_text: str | None
    span_start: int | None
    span_end: int | None
    tokens: int
    # #44: `tokens` alone (total) cannot be priced — gpt-4o-mini charges 4x for output, so a
    # total-token figure only bounds the cost between an all-input and an all-output extreme,
    # which is what the #28 run had to publish. Split counts make the dollar figure exact.
    model: str = MODEL
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


@lru_cache(maxsize=2)
def _client(api_key: str) -> Any:
    """One client per key, shared across the run's threads.

    #44: building an `OpenAI()` inside `predict` left a fresh connection pool per call. Over a
    1,704-call run the process's established sockets climbed steadily — a file-descriptor
    exhaustion waiting to happen, hundreds of calls after the point where it would be cheap to
    restart. The SDK's client is thread-safe, so one instance is both correct and cheaper.

    Cached on the key, so a caller passing a different key still gets its own client. The key
    never leaves this process and is never logged.
    """
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def option_ids(allowed_positions: list[str]) -> dict[str, str]:
    """Short, schema-safe ids for a deal point's position vocabulary.

    #44: MAUD position values are free text and 13 deal points have one containing a double
    quote, which OpenAI's `strict: true` structured outputs reject inside an enum literal. Put
    the literals in the prompt and the ids in the enum: the answer is still constrained to a
    closed set, so an invalid answer remains undecidable, and the schema stays valid whatever
    punctuation an annotator used. It also keeps the enum small — one deal point's positions run
    to 8,512 characters.
    """
    return {f"p{i:02d}": position for i, position in enumerate(allowed_positions, start=1)}


def response_schema(options: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "position": {"type": "string", "enum": list(options)},
            "quote": {
                "type": "string",
                "description": "The exact supporting sentence, copied verbatim from the "
                "contract. Empty string if the answer is inferred from absence.",
            },
        },
        "required": ["position", "quote"],
        "additionalProperties": False,
    }


def decode_option(options: dict[str, str], option_id: str) -> str:
    """An id outside the map decodes to "", never to a nearby option — a plausible substitute
    would be graded as a real prediction."""
    return options.get(option_id, "")


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
    client = _client(api_key)
    context = contract_text[:CONTEXT_CHARS]

    options = option_ids(allowed_positions)
    schema = response_schema(options)
    option_list = "\n".join(f"{key} = {value}" for key, value in options.items())

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are labelling a merger agreement for the ABA-style deal point "
                    f'"{deal_point_name}". Choose exactly one position from the allowed set '
                    "below and answer with its id alone, then quote the exact sentence that "
                    f"supports it, copied verbatim.\n\n{option_list}"
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
    position = decode_option(options, content.get("position", ""))
    usage = response.usage
    tokens = usage.total_tokens if usage else 0
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    call_cost = cost_usd(MODEL, prompt_tokens, completion_tokens)

    start, end = _locate(context, content.get("quote", ""))
    # The structured log is the audit trail the run's committed dollar figure is reconciled
    # against — CLAUDE.md requires each LLM call to log model, tokens, and cost.
    log.info(
        "calibration_prediction",
        matter_id=matter_id,
        deal_point_name=deal_point_name,
        predicted=position,
        model=MODEL,
        tokens=tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=call_cost,
        located=start is not None,
    )
    return Prediction(
        matter_id=matter_id,
        deal_point_name=deal_point_name,
        predicted_position=position,
        quoted_text=content.get("quote") or None,
        span_start=start,
        span_end=end,
        tokens=tokens,
        model=MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=call_cost,
    )
