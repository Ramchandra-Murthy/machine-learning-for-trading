"""Unit tests for RP-2 canonical data schemas and policy rules."""

from dataclasses import FrozenInstanceError, fields
from datetime import date
from pathlib import Path

import pytest

from india_ml4t.data.policy import (
    POLICY_VERSION,
    ReasonCodes,
    classify_isin_prefix,
)
from india_ml4t.data.schemas import (
    LISTING_DF_COLUMNS,
    SECURITY_DF_COLUMNS,
    DuplicateIsinDiagnostic,
    ExchangeListingRecord,
    NSEMasterParseResult,
    SecurityRecord,
    SymbolHistoryRecord,
)


def make_parse_result(**overrides):
    values = {
        "as_of_date": date(2026, 11, 18),
        "source_file": Path("NSE_CM_security_18112026.csv.gz"),
        "source_checksum": "test-checksum",
        "parser_version": "test-parser",
        "policy_version": POLICY_VERSION,
        "total_source_rows": 10,
        "valid_listing_rows": 8,
        "unique_isin_count": 7,
        "duplicate_isin_count": 1,
        "rejected_row_count": 2,
    }
    values.update(overrides)
    return NSEMasterParseResult(**values)


def test_security_record_is_separate_from_exchange_listing():
    security_fields = {item.name for item in fields(SecurityRecord)}
    listing_fields = {item.name for item in fields(ExchangeListingRecord)}

    assert {"isin", "security_name", "isin_category"} <= security_fields
    assert "exchange" not in security_fields
    assert "fin_instrm_id" not in security_fields
    assert {"exchange", "fin_instrm_id", "tckr_symb", "scty_srs"} <= listing_fields


def test_symbol_history_separates_observation_and_effective_dates():
    history_fields = {item.name for item in fields(SymbolHistoryRecord)}

    assert "observed_on" in history_fields
    assert "effective_from" in history_fields
    assert "effective_to" in history_fields

    record = SymbolHistoryRecord(
        isin="INE002A01018",
        exchange="NSE",
        tckr_symb="TCS",
        observed_on=date(2026, 11, 18),
    )

    assert record.observed_on == date(2026, 11, 18)
    assert record.effective_from is None
    assert record.effective_to is None


def test_empty_dataframe_helpers_keep_fixed_column_contracts():
    result = make_parse_result()

    listings = result.to_listings_dataframe()
    securities = result.to_securities_dataframe()

    assert listings.empty
    assert tuple(listings.columns) == LISTING_DF_COLUMNS
    assert securities.empty
    assert tuple(securities.columns) == SECURITY_DF_COLUMNS


def test_dataframe_helpers_sort_rows_deterministically():
    result = make_parse_result(
        listings=(
            ExchangeListingRecord(
                isin="INE002A01018",
                exchange="NSE",
                fin_instrm_id="2",
                tckr_symb="TCS",
                scty_srs="EQ",
            ),
            ExchangeListingRecord(
                isin="INE001A01036",
                exchange="NSE",
                fin_instrm_id="1",
                tckr_symb="RELIANCE",
                scty_srs="EQ",
            ),
        ),
        securities=(
            SecurityRecord(isin="INE002A01018", security_name="TCS"),
            SecurityRecord(isin="INE001A01036", security_name="RELIANCE"),
        ),
    )

    assert result.to_listings_dataframe()["isin"].tolist() == [
        "INE001A01036",
        "INE002A01018",
    ]
    assert result.to_securities_dataframe()["isin"].tolist() == [
        "INE001A01036",
        "INE002A01018",
    ]


def test_duplicate_isin_count_means_distinct_isins_not_excess_rows():
    diagnostics = (
        DuplicateIsinDiagnostic(
            isin="INE001A01036",
            exchange="NSE",
            record_count=3,
            symbols=("ABC", "ABCOLD"),
            fin_instrm_ids=("1", "2", "3"),
            series_list=("EQ",),
            reason_code="DUPLICATE_ISIN",
        ),
        DuplicateIsinDiagnostic(
            isin="INE002A01018",
            exchange="NSE",
            record_count=2,
            symbols=("XYZ",),
            fin_instrm_ids=("4", "5"),
            series_list=("EQ",),
            reason_code="DUPLICATE_ISIN",
        ),
    )

    result = make_parse_result(
        total_source_rows=5,
        valid_listing_rows=5,
        unique_isin_count=2,
        duplicate_isin_count=2,
        duplicate_isin_diagnostics=diagnostics,
    )

    # Two distinct duplicated ISINs, despite three excess source rows.
    assert result.duplicate_isin_count == 2
    assert len(result.duplicate_isin_diagnostics) == 2
    assert sum(item.record_count - 1 for item in diagnostics) == 3


@pytest.mark.parametrize(
    ("isin", "expected"),
    [
        (None, "MISSING"),
        ("", "MISSING"),
        ("   ", "MISSING"),
        ("INE002A01018", "INE_EQUITY"),
        ("INF123A01010", "INF_SCHEME"),
        ("DUMMY0000292", "DUMMY_TEST"),
        ("ABC123", "MALFORMED"),
        ("1234567890123", "MALFORMED"),
        ("US0378331005", "OTHER"),
    ],
)
def test_classify_isin_prefix(isin, expected):
    assert classify_isin_prefix(isin) == expected


def test_isin_classification_is_structural_not_checksum_validation():
    # A 12-character INE-prefixed value is classified structurally.
    # This function does not establish ISO 6166 checksum validity
    # or whether the security is eligible for trading.
    assert classify_isin_prefix("INE000000000") == "INE_EQUITY"


def test_missing_symbol_and_instrument_id_reason_codes_are_distinct():
    assert ReasonCodes.MISSING_TICKER_SYMBOL.code == "MISSING_TICKER_SYMBOL"
    assert ReasonCodes.MISSING_INSTRUMENT_ID.code == "MISSING_INSTRUMENT_ID"
    assert ReasonCodes.MISSING_TICKER_SYMBOL.code != ReasonCodes.MISSING_INSTRUMENT_ID.code


def test_schema_records_are_immutable():
    security = SecurityRecord(isin="INE002A01018")

    with pytest.raises(FrozenInstanceError):
        security.isin = "INE001A01036"
