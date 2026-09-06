"""The minimal calibration extractor's answer channel (#28, hardened in #44).

The model picks from the deal point's own observed position vocabulary. #28 put those strings
straight into a JSON-schema `enum` under `strict: true`, which held for the five hand-picked
deal points it calibrated. Widening to all 92 broke it: 13 deal points have a position value
containing a double quote, and OpenAI rejects a strict enum whose literals contain one —

    Invalid schema for response_format 'deal_point_prediction': In context=('properties',
    'position'), " is not allowed in string literals for structured outputs (strict=true)

so the run 400s before a single prediction lands. The fix keeps the constraint and moves the
literals out of the schema: the enum holds short option ids, the prose holds the positions, and
an id that is not in the map decodes to "" rather than to a guess.

Runs with `OPENAI_API_KEY` unset — these are pure functions, no call is made.
"""

from __future__ import annotations

from explorer.evals.context import Passage
from explorer.evals.extract_deal_point import (
    build_messages,
    decode_option,
    option_ids,
    response_schema,
)
from explorer.evals.fewshot import Example


class TestOptionIds:
    def test_ids_are_stable_and_one_per_position(self) -> None:
        options = option_ids(["No", "Yes"])
        assert list(options) == ["p01", "p02"]
        assert options == {"p01": "No", "p02": "Yes"}

    def test_ids_stay_sorted_past_nine_so_the_prompt_reads_in_order(self) -> None:
        options = option_ids([f"position {i}" for i in range(12)])
        assert list(options) == sorted(options)

    def test_no_id_contains_a_character_a_strict_enum_rejects(self) -> None:
        options = option_ids(['A "quoted" answer', "Plain"])
        assert all(i.isalnum() for i in options)


class TestResponseSchema:
    def test_positions_with_quotes_never_reach_the_schema(self) -> None:
        """The regression this file exists for."""
        schema = response_schema(option_ids(['"Ability to consummate" carveout', "None"]))
        enum = schema["properties"]["position"]["enum"]
        assert enum == ["p01", "p02"]
        assert not any('"' in value for value in enum)

    def test_the_schema_stays_strict_and_closed(self) -> None:
        schema = response_schema(option_ids(["Yes", "No"]))
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"position", "quote"}


class TestDecodeOption:
    def test_a_known_id_decodes_to_its_position_verbatim(self) -> None:
        options = option_ids(['A "quoted" answer', "Plain"])
        assert decode_option(options, "p01") == 'A "quoted" answer'

    def test_an_unknown_id_decodes_to_empty_not_to_a_nearby_option(self) -> None:
        """A wrong-but-plausible position would be graded as a real prediction. An empty one is
        graded as wrong, which is what an unusable answer is."""
        assert decode_option(option_ids(["Yes"]), "p99") == ""
        assert decode_option(option_ids(["Yes"]), "") == ""


class TestThePromptTheModelActuallyGets:
    """#58 changed two things about the prompt: the contract text is retrieved rather than
    truncated, and the option list is now preceded by worked examples. `build_messages` is
    where both land, and it is pure, so the assembled prompt is checkable without a call."""

    def _passages(self) -> list[Passage]:
        return [Passage(328_710, 328_730, "Material Adverse")]

    def test_with_no_examples_it_is_the_two_turn_shape_44_sent(self) -> None:
        """The control has to remain expressible, or the before/after table compares a current
        run against a remembered one."""
        messages = build_messages(
            "Some deal point", option_ids(["Yes", "No"]), self._passages(), examples=[]
        )
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_the_option_list_is_still_in_the_system_turn(self) -> None:
        messages = build_messages("Some deal point", option_ids(["Yes", "No"]), self._passages())
        assert "p01 = Yes" in messages[0]["content"]
        assert "Some deal point" in messages[0]["content"]

    def test_examples_come_before_the_contract_under_test(self) -> None:
        """An example after the question reads as part of the document being classified."""
        options = option_ids(["Yes", "No"])
        example = Example("contract_130", "Yes", 0, 9, "some text", "some text")
        messages = build_messages("Some deal point", options, self._passages(), [example])
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
        assert "contract_130" in messages[1]["content"]
        assert "Material Adverse" in messages[-1]["content"]

    def test_the_contract_turn_carries_the_document_character_ranges(self) -> None:
        """The excerpts are non-contiguous. Unmarked, three disjoint pieces of an agreement read
        as one continuous passage."""
        content = build_messages("Some deal point", option_ids(["Yes"]), self._passages())[-1][
            "content"
        ]
        assert "328710" in content
