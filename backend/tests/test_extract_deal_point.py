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

from explorer.evals.extract_deal_point import decode_option, option_ids, response_schema


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
