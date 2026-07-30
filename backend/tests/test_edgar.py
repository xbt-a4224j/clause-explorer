"""EDGAR enrichment: header parsing, party roles, SIC -> FOLIO (#9).

Every test here runs **offline**. Identification is a pure function of the contract header
plus a CIK index; the only network step is fetching a company's submissions JSON, and that is
exercised against a cached fixture. A test suite that needs sec.gov is a test suite that goes
red when sec.gov rate-limits.
"""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
from explorer.ingest.edgar import (
    SicFolioMap,
    normalize_company_name,
    parse_header,
    resolve_cik,
    submissions_to_facts,
)

HEADERS = {
    # acquirer first, sub keyword, target last
    "contract_0": (
        "Exhibit 2.1 Execution Version AMENDED AND RESTATED AGREEMENT AND PLAN OF MERGER "
        "BY AND AMONG CISCO SYSTEMS, INC., AMARONE ACQUISITION CORP. AND ACACIA "
        "COMMUNICATIONS, INC. JANUARY 14, 2021 TABLE OF CONTENTS"
    ),
    # target FIRST — the case that breaks a "target is last" rule
    "contract_2": (
        "Exhibit 2.1 EXECUTION COPY AGREEMENT AND PLAN OF MERGER by and among: ADAMAS "
        "PHARMACEUTICALS, INC., SUPERNUS PHARMACEUTICALS, INC., and SUPERNUS REEF, INC. "
        "Dated as of October 10, 2021 TABLE OF CONTENTS"
    ),
    # acquirer and sub share a name stem
    "contract_3": (
        "EXHIBIT 2.1 AGREEMENT AND PLAN OF MERGER among CARTER INTERMEDIATE, INC., CARTER "
        "ACQUISITION, INC. and AEGION CORPORATION Dated as of February 16, 2021 TABLE OF CONTENTS"
    ),
}


class TestParseHeader:
    def test_signing_date_is_read_from_the_document(self) -> None:
        assert parse_header(HEADERS["contract_2"]).signing_date.isoformat() == "2021-10-10"

    def test_uppercase_date_is_read_too(self) -> None:
        """`JANUARY 14, 2021` — a case-sensitive month pattern silently loses 18 of 152."""
        assert parse_header(HEADERS["contract_0"]).signing_date.isoformat() == "2021-01-14"

    def test_target_is_the_party_that_is_not_acquirer_or_merger_sub(self) -> None:
        assert parse_header(HEADERS["contract_0"]).target_name == "ACACIA COMMUNICATIONS, INC."

    def test_target_first_is_handled_by_the_shared_stem_rule(self) -> None:
        """SUPERNUS + SUPERNUS REEF share a stem, so they are the buy side; ADAMAS is the
        target even though it is listed first."""
        parsed = parse_header(HEADERS["contract_2"])
        assert parsed.target_name == "ADAMAS PHARMACEUTICALS, INC."
        assert parsed.acquirer_name == "SUPERNUS PHARMACEUTICALS, INC."

    def test_shared_stem_with_an_acquisition_sub(self) -> None:
        parsed = parse_header(HEADERS["contract_3"])
        assert parsed.target_name == "AEGION CORPORATION"
        assert parsed.acquirer_name == "CARTER INTERMEDIATE, INC."

    def test_unparseable_header_yields_nones_not_guesses(self) -> None:
        parsed = parse_header("THIS AGREEMENT is made between the parties hereto.")
        assert parsed.target_name is None
        assert parsed.signing_date is None


class TestCikResolution:
    INDEX: ClassVar[dict[str, str]] = {
        "ACACIA COMMUNICATIONS INC": "0001651235",
        "AEGION CORP": "0000353020",
        "ADAMAS PHARMACEUTICALS INC": "0001328143",
    }

    def test_normalization_drops_punctuation_and_legal_suffix_variants(self) -> None:
        assert normalize_company_name("Acacia Communications, Inc.") == "ACACIA COMMUNICATIONS INC"

    def test_exact_after_normalization(self) -> None:
        assert resolve_cik("ACACIA COMMUNICATIONS, INC.", self.INDEX) == "0001651235"

    def test_corporation_and_corp_are_the_same_company(self) -> None:
        assert resolve_cik("AEGION CORPORATION", self.INDEX) == "0000353020"

    def test_unknown_company_is_none(self) -> None:
        assert resolve_cik("WHITE SANDS PARENT, INC.", self.INDEX) is None


class TestSicToFolio:
    @pytest.fixture(scope="class")
    def mapping(self) -> SicFolioMap:
        return SicFolioMap.load()

    def test_major_group_maps(self, mapping: SicFolioMap) -> None:
        assert mapping.resolve("2834") == "RBOjgvcq6Z33XxMhTxWiiDS"  # pharma -> Manufacturing

    def test_four_digit_row_overrides_its_major_group(self, mapping: SicFolioMap) -> None:
        """SIC files software under Services; NAICS and FOLIO put it under Information."""
        assert mapping.resolve("7372") == "RHwCmZ2yKrJobzC86GC6Ep"
        assert mapping.resolve("7389") == "RN2D91ENKaHvvID40zUJvt"

    def test_health_services(self, mapping: SicFolioMap) -> None:
        assert mapping.resolve("8060") == "RCSG4k3ah1Pu5YgPexPgOmL"

    def test_unmapped_sic_is_none_not_a_default_bucket(self, mapping: SicFolioMap) -> None:
        assert mapping.resolve("") is None
        assert mapping.resolve("05") is None


SUBMISSIONS_FIXTURE = json.dumps(
    {
        "cik": "1651235",
        "name": "Acacia Communications, Inc.",
        "sic": "3674",
        "sicDescription": "Semiconductors & Related Devices",
    }
)


class TestSubmissionsParsing:
    def test_extracts_sic_and_name(self) -> None:
        facts = submissions_to_facts(json.loads(SUBMISSIONS_FIXTURE))
        assert facts.sic == "3674"
        assert facts.name == "Acacia Communications, Inc."

    def test_missing_sic_is_none(self) -> None:
        facts = submissions_to_facts({"name": "Private Co", "sic": ""})
        assert facts.sic is None


class TestClientIsOfflineOnceCached:
    """The AC: re-runs make no network calls, and the suite runs with no network at all."""

    def test_cached_response_is_returned_without_fetching(self, tmp_path) -> None:
        from explorer.ingest.edgar import EdgarClient

        (tmp_path / "CIK0001651235.json").write_text(SUBMISSIONS_FIXTURE)
        client = EdgarClient(cache_dir=tmp_path, offline=True)
        assert submissions_to_facts(client.submissions("0001651235")).sic == "3674"
        assert client.requests_made == 0

    def test_offline_miss_is_none_not_an_exception(self, tmp_path) -> None:
        from explorer.ingest.edgar import EdgarClient

        client = EdgarClient(cache_dir=tmp_path, offline=True)
        assert client.submissions("0000000000") is None
        assert client.requests_made == 0
