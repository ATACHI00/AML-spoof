"""Tests for the OFAC SDN provider (parser and downloader)."""

from __future__ import annotations

import pytest

from app.services.sanctions_provider import _extract_aliases, _parse_sdn_csv_row, parse_sdn_csv


class TestExtractAliases:
    """Tests for alias extraction from OFAC remarks."""

    def test_aka_pattern(self) -> None:
        remarks = "a.k.a. JOHN DOE; a.k.a. JOHNNY DOE"
        aliases = _extract_aliases(remarks)
        assert "JOHN DOE" in aliases
        assert "JOHNNY DOE" in aliases

    def test_fka_pattern(self) -> None:
        remarks = "f.k.a. SMITH CORP"
        aliases = _extract_aliases(remarks)
        assert "SMITH CORP" in aliases

    def test_no_aliases(self) -> None:
        remarks = "No alias information available"
        aliases = _extract_aliases(remarks)
        assert aliases == []

    def test_empty_remarks(self) -> None:
        assert _extract_aliases("") == []

    def test_multiple_aka_variants(self) -> None:
        remarks = "aka BAD GUY; a.k.a. EVIL CORP; n.k.a. NEW NAME"
        aliases = _extract_aliases(remarks)
        assert "BAD GUY" in aliases
        assert "EVIL CORP" in aliases
        assert "NEW NAME" in aliases


class TestParseSdnCsvRow:
    """Tests for parsing a single OFAC SDN CSV row."""

    def test_individual_row(self) -> None:
        row = [
            "1", "JOHN DOE", "individual", "UKRAINE-EO13662",
            "", "", "", "", "", "", "", "a.k.a. JOHNNY DOE",
            "123 Main St", "Washington", "DC", "20001", "US", "",
        ]
        parsed = _parse_sdn_csv_row(row)
        assert parsed is not None
        assert parsed["full_name"] == "JOHN DOE"
        assert parsed["list_source"] == "ofac"
        assert parsed["entity_type"] == "individual"
        assert parsed["program"] == "UKRAINE-EO13662"
        assert parsed["country"] == "US"
        assert parsed["name_variations"] == ["JOHNNY DOE"]

    def test_entity_row(self) -> None:
        row = [
            "2", "EVIL CORP LTD", "entity", "SDGT",
            "", "", "", "", "", "", "", "",
            "PO Box 123", "", "", "", "IR", "",
        ]
        parsed = _parse_sdn_csv_row(row)
        assert parsed is not None
        assert parsed["full_name"] == "EVIL CORP LTD"
        assert parsed["entity_type"] == "entity"
        assert parsed["country"] == "IR"
        assert parsed["program"] == "SDGT"

    def test_short_row(self) -> None:
        row = ["1", "NAME"]
        parsed = _parse_sdn_csv_row(row)
        assert parsed is None

    def test_empty_name(self) -> None:
        row = ["1", "", "individual", "PROG"]
        parsed = _parse_sdn_csv_row(row)
        assert parsed is None


class TestParseSdnCsv:
    """Tests for parsing full OFAC SDN CSV content."""

    CSV_HEADER = "ent_num,SDN_Name,SDN_Type,Program,Title,Call_Sign,Vess_type,Tonnage,GRT,Vess_flag,Vess_owner,Remarks,Address,City,State/Province,Postal_Code,Country,Other\n"

    def test_parse_single_row(self) -> None:
        content = (
            self.CSV_HEADER
            + '1,"JOHN DOE","individual","UKRAINE-EO13662","","","","","","","","a.k.a. JOHNNY DOE","123 Main St","Washington","DC","20001","US",""\n'
        )
        records = parse_sdn_csv(content)
        assert len(records) == 1
        assert records[0]["full_name"] == "JOHN DOE"

    def test_parse_multiple_rows(self) -> None:
        content = (
            self.CSV_HEADER
            + '1,"JOHN DOE","individual","PROG1","","","","","","","","","","","","","US",""\n'
            + '2,"EVIL CORP","entity","PROG2","","","","","","","","","","","","","IR",""\n'
        )
        records = parse_sdn_csv(content)
        assert len(records) == 2

    def test_skip_header(self) -> None:
        content = self.CSV_HEADER
        records = parse_sdn_csv(content)
        assert len(records) == 0

    def test_skip_empty_rows(self) -> None:
        content = self.CSV_HEADER + "\n\n"
        records = parse_sdn_csv(content)
        assert len(records) == 0

    def test_quoted_fields_with_commas(self) -> None:
        content = (
            self.CSV_HEADER
            + '1,"DOE, JOHN","individual","PROG","","","","","","","","","","","","","US",""\n'
        )
        records = parse_sdn_csv(content)
        assert len(records) == 1
        assert records[0]["full_name"] == "DOE, JOHN"