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
from explorer.evals.context import CONTEXT_CHARS, Passage, locate, prefix_passages, render
from explorer.evals.fewshot import Example, as_messages
from explorer.evals.pricing import cost_usd

log = get_logger()

# #58: the window used to be `contract_text[:CONTEXT_CHARS]`, on the rationale that the answers
# are "disproportionately front-loaded" in a merger agreement. Measurement did not support it —
# on contract_10 that window is 1.6% of the agreement and contains none of the MAE definition
# the question is about. The budget is unchanged at 12,000 characters; *which* 12,000 is now
# decided by hybrid retrieval (`evals/context.py`). A caller that passes no passages still gets
# the prefix, so the control run stays reproducible from this same code.
__all__ = [
    "CONTEXT_CHARS",
    "Prediction",
    "build_messages",
    "decode_option",
    "option_ids",
    "predict",
    "response_schema",
]


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
    # #58: what the model was actually shown, recorded per call, so a reader of the predictions
    # file can tell a retrieval run from the prefix control without consulting the report.
    context_mode: str = "prefix"
    context_chars: int = 0
    passage_count: int = 1
    example_count: int = 0
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


def build_messages(
    deal_point_name: str,
    options: dict[str, str],
    passages: list[Passage],
    examples: list[Example] | None = None,
) -> list[dict[str, str]]:
    """The whole prompt, assembled without calling anything.

    Order is system, then the worked examples as user/assistant pairs, then the contract under
    test last. An example placed after the question reads as part of the document being
    classified, which is the one arrangement that makes a few-shot prompt worse than none.
    """
    option_list = "\n".join(f"{key} = {value}" for key, value in options.items())
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are labelling a merger agreement for the ABA-style deal point "
                f'"{deal_point_name}". Choose exactly one position from the allowed set '
                "below and answer with its id alone, then quote the exact sentence that "
                "supports it, copied verbatim.\n\nThe agreement is supplied as excerpts, each "
                "under the character range it was cut from. Quote only contract text, never a "
                f"[chars ...] marker.\n\n{option_list}"
            ),
        }
    ]
    messages.extend(as_messages(examples or [], options))
    messages.append({"role": "user", "content": render(passages)})
    return messages


def predict(
    matter_id: str,
    contract_text: str,
    deal_point_name: str,
    allowed_positions: list[str],
    api_key: str,
    passages: list[Passage] | None = None,
    examples: list[Example] | None = None,
    context_mode: str = "prefix",
) -> Prediction:
    client = _client(api_key)
    # No passages means the #44 behaviour, byte for byte: the first CONTEXT_CHARS characters.
    shown = passages if passages is not None else prefix_passages(contract_text)

    options = option_ids(allowed_positions)
    schema = response_schema(options)
    messages = build_messages(deal_point_name, options, shown, examples)

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,  # type: ignore[arg-type]
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

    start, end = locate(shown, contract_text, content.get("quote", ""))
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
        context_mode=context_mode,
        context_chars=sum(p.end - p.start for p in shown),
        passage_count=len(shown),
        example_count=len(examples or []),
    )
    return Prediction(
        matter_id=matter_id,
        deal_point_name=deal_point_name,
        predicted_position=position,
        quoted_text=content.get("quote") or None,
        span_start=start,
        span_end=end,
        tokens=tokens,
        context_mode=context_mode,
        context_chars=sum(p.end - p.start for p in shown),
        passage_count=len(shown),
        example_count=len(examples or []),
        model=MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=call_cost,
    )
