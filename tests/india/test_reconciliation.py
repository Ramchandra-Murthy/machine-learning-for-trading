"""Synthetic unit tests for cross-exchange NSE and BSE reconciliation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from india_ml4t.data.policy import ReasonCodes
from india_ml4t.data.reconciliation import (
    RECONCILIATION_VERSION,
    reconcile_security_masters,
)
from india_ml4t.data.schemas import (
    DuplicateIsinDiagnostic,
    ExchangeListingRecord,
    RejectedRecord,
    SecurityMasterParseResult,
    SecurityRecord,
)

AS_OF = date(2026, 11, 18)


def test_reconcile_common_nse_only_bse_only_duplicates_and_exceptions() -> None:
    nse_listings = (
        ExchangeListingRecord(
            isin="INE002A01018",
            exchange="NSE",
            fin_instrm_id="2885",
            tckr_symb="RELIANCE",
            scty_srs="EQ",
            fin_instrm_nm="Reliance Industries Limited",
            as_of_date=AS_OF,
            source_file="nse_master.csv",
        ),
        ExchangeListingRecord(
            isin="INE009A01021",
            exchange="NSE",
            fin_instrm_id="1660",
            tckr_symb="INFY",
            scty_srs="EQ",
            fin_instrm_nm="Infosys Limited",
            del_flg="Y",
            rmvl_dt="20261117",
            as_of_date=AS_OF,
            source_file="nse_master.csv",
        ),
    )

    bse_listings = (
        ExchangeListingRecord(
            isin="INE002A01018",
            exchange="BSE",
            fin_instrm_id="500325",
            tckr_symb="RELIANCE",
            scty_srs="A",
            fin_instrm_nm="RELIANCE INDUSTRIES LTD.",
            listing_status="A",
            as_of_date=AS_OF,
            source_file="BSE_SCRIP.zip",
        ),
        ExchangeListingRecord(
            isin="INE001A01036",
            exchange="BSE",
            fin_instrm_id="500112",
            tckr_symb="HOUSING",
            scty_srs="B",
            fin_instrm_nm="Housing Dev Fin Corp",
            listing_status="A",
            as_of_date=AS_OF,
            source_file="BSE_SCRIP.zip",
        ),
        ExchangeListingRecord(
            isin="INE001A01036",
            exchange="BSE",
            fin_instrm_id="590112",
            tckr_symb="HOUSING#",
            scty_srs="T",
            fin_instrm_nm="Housing Dev Fin Corp",
            listing_status="S",
            rmvl_dt="20261117",
            as_of_date=AS_OF,
            source_file="BSE_SCRIP.zip",
        ),
    )

    nse_result = SecurityMasterParseResult(
        as_of_date=AS_OF,
        source_file=Path("D:/ML4T_data/nse_master.csv"),
        source_checksum="nse-sha256-abc",
        parser_version="gate1b-nse-master-v0.1.0",
        policy_version="gate1-policy-v0.1.0",
        total_source_rows=3,
        valid_listing_rows=2,
        unique_isin_count=2,
        duplicate_isin_count=0,
        rejected_row_count=1,
        securities=(
            SecurityRecord(
                isin="INE002A01018",
                security_name="Reliance Industries Limited",
                isin_category="INE_EQUITY",
            ),
            SecurityRecord(
                isin="INE009A01021",
                security_name="Infosys Limited",
                isin_category="INE_EQUITY",
            ),
        ),
        listings=nse_listings,
        rejected_records=(
            RejectedRecord(
                row_number=4,
                reason_code=ReasonCodes.MISSING_ISIN.code,
                detail=ReasonCodes.MISSING_ISIN.description,
                raw_symbol="BADNSE",
                raw_fin_instrm_id="9999",
                source_file="nse_master.csv",
            ),
        ),
    )

    bse_result = SecurityMasterParseResult(
        as_of_date=AS_OF,
        source_file=Path("D:/ML4T_data/BSE_SCRIP.zip"),
        source_checksum="bse-member-sha256-def",
        parser_version="gate1c-bse-master-v0.1.0",
        policy_version="gate1-policy-v0.1.0",
        total_source_rows=4,
        valid_listing_rows=3,
        unique_isin_count=2,
        duplicate_isin_count=1,
        rejected_row_count=1,
        securities=(
            SecurityRecord(
                isin="INE002A01018",
                security_name="RELIANCE INDUSTRIES LTD.",
                isin_category="INE_EQUITY",
            ),
            SecurityRecord(
                isin="INE001A01036",
                security_name="Housing Dev Fin Corp",
                isin_category="INE_EQUITY",
            ),
        ),
        listings=bse_listings,
        duplicate_isin_diagnostics=(
            DuplicateIsinDiagnostic(
                isin="INE001A01036",
                exchange="BSE",
                record_count=2,
                symbols=("HOUSING", "HOUSING#"),
                fin_instrm_ids=("500112", "590112"),
                series_list=("B", "T"),
                reason_code=ReasonCodes.DUPLICATE_ISIN.code,
                as_of_date=AS_OF,
                source_file="BSE_SCRIP.zip",
            ),
        ),
        rejected_records=(
            RejectedRecord(
                row_number=1620,
                reason_code=ReasonCodes.MALFORMED_ISIN.code,
                detail=ReasonCodes.MALFORMED_ISIN.description,
                raw_isin="NA",
                raw_symbol="ESSRINV",
                raw_fin_instrm_id="501156",
                source_file="BSE_SCRIP.zip",
            ),
        ),
    )

    first = reconcile_security_masters(nse_result, bse_result)
    second = reconcile_security_masters(nse_result, bse_result)

    assert first == second
    assert first.summary is not None

    summary = first.summary
    assert summary.reconciliation_version == RECONCILIATION_VERSION
    assert summary.nse_source_checksum == "nse-sha256-abc"
    assert summary.bse_source_checksum == "bse-member-sha256-def"
    assert summary.common_isin_count == 1
    assert summary.nse_only_isin_count == 1
    assert summary.bse_only_isin_count == 1
    assert summary.total_unique_isins == 3
    assert summary.nse_valid_listings == 2
    assert summary.bse_valid_listings == 3
    assert summary.duplicate_group_count == 1
    assert summary.exception_count == 2

    by_isin = {row.isin: row for row in first.cross_exchange_master}

    common = by_isin["INE002A01018"]
    assert common.match_category == "COMMON"
    assert common.nse_listing_count == 1
    assert common.bse_listing_count == 1
    assert common.has_duplicate is False

    nse_only = by_isin["INE009A01021"]
    assert nse_only.match_category == "NSE_ONLY"
    assert nse_only.nse_listing_count == 1
    assert nse_only.bse_listing_count == 0

    bse_only = by_isin["INE001A01036"]
    assert bse_only.match_category == "BSE_ONLY"
    assert bse_only.bse_listing_count == 2
    assert bse_only.has_bse_duplicate is True
    assert bse_only.has_nse_duplicate is False
    assert bse_only.has_duplicate is True

    # Every valid listing must survive reconciliation.
    assert len(first.exchange_listing_comparison) == 5

    bse_housing_rows = [
        row for row in first.exchange_listing_comparison if row.isin == "INE001A01036"
    ]
    assert len(bse_housing_rows) == 2
    assert {row.fin_instrm_id for row in bse_housing_rows} == {
        "500112",
        "590112",
    }

    # Deleted NSE listing must be retained with its source status and removal date.
    deleted_nse = next(row for row in first.exchange_listing_comparison if row.tckr_symb == "INFY")
    assert deleted_nse.del_flg == "Y"
    assert deleted_nse.rmvl_dt == "20261117"

    # Suspended BSE listing must be retained with its source status and removal date.
    suspended_bse = next(
        row for row in first.exchange_listing_comparison if row.fin_instrm_id == "590112"
    )
    assert suspended_bse.listing_status == "S"
    assert suspended_bse.rmvl_dt == "20261117"

    # Duplicate diagnostic must be preserved and classified.
    assert len(first.duplicate_groups) == 1
    duplicate = first.duplicate_groups[0]
    assert duplicate.exchange == "BSE"
    assert duplicate.isin == "INE001A01036"
    assert duplicate.duplicate_category == "INE"
    assert duplicate.record_count == 2

    # Rejected source records must become exceptions.
    assert [(row.exchange, row.row_number, row.reason_code) for row in first.exceptions] == [
        ("BSE", 1620, ReasonCodes.MALFORMED_ISIN.code),
        ("NSE", 4, ReasonCodes.MISSING_ISIN.code),
    ]

    assert all(row.as_of_date == AS_OF for row in first.exceptions)


@pytest.mark.parametrize(
    ("isin", "isin_category", "expected_duplicate_category"),
    [
        ("INE111A01010", "INE_EQUITY", "INE"),
        ("INF111A01010", "INF_SCHEME", "INF"),
        ("DUM111A01010", "DUMMY_TEST", "DUMMY"),
        ("OTH111A01010", "UNKNOWN", "OTHER"),
    ],
)
def test_duplicate_categories_are_classified(
    isin: str,
    isin_category: str,
    expected_duplicate_category: str,
) -> None:
    diagnostic = DuplicateIsinDiagnostic(
        isin=isin,
        exchange="BSE",
        record_count=2,
        symbols=("TEST", "TEST-A"),
        fin_instrm_ids=("100001", "100002"),
        series_list=("A", "B"),
        reason_code=ReasonCodes.DUPLICATE_ISIN.code,
        as_of_date=AS_OF,
        source_file="BSE_SCRIP.zip",
    )

    nse_result = SecurityMasterParseResult(
        as_of_date=AS_OF,
        source_file=Path("nse.csv"),
        source_checksum="nse-test",
        parser_version="nse-v1",
        policy_version="policy-v1",
        total_source_rows=0,
        valid_listing_rows=0,
        unique_isin_count=0,
        duplicate_isin_count=0,
        rejected_row_count=0,
    )

    bse_result = SecurityMasterParseResult(
        as_of_date=AS_OF,
        source_file=Path("bse.csv"),
        source_checksum="bse-test",
        parser_version="bse-v1",
        policy_version="policy-v1",
        total_source_rows=2,
        valid_listing_rows=2,
        unique_isin_count=1,
        duplicate_isin_count=1,
        rejected_row_count=0,
        securities=(
            SecurityRecord(
                isin=isin,
                isin_category=isin_category,
            ),
        ),
        duplicate_isin_diagnostics=(diagnostic,),
    )

    result = reconcile_security_masters(nse_result, bse_result)

    assert len(result.duplicate_groups) == 1
    expected_isin_category = "OTHER" if isin_category == "UNKNOWN" else isin_category
    assert result.duplicate_groups[0].isin_category == expected_isin_category
    assert result.duplicate_groups[0].duplicate_category == expected_duplicate_category


def test_reconciliation_rejects_mismatched_dates_without_override() -> None:
    nse_result = SecurityMasterParseResult(
        as_of_date=AS_OF,
        source_file=Path("nse.csv"),
        source_checksum="nse",
        parser_version="nse-v1",
        policy_version="policy-v1",
        total_source_rows=0,
        valid_listing_rows=0,
        unique_isin_count=0,
        duplicate_isin_count=0,
        rejected_row_count=0,
    )

    bse_result = SecurityMasterParseResult(
        as_of_date=date(2026, 11, 17),
        source_file=Path("bse.csv"),
        source_checksum="bse",
        parser_version="bse-v1",
        policy_version="policy-v1",
        total_source_rows=0,
        valid_listing_rows=0,
        unique_isin_count=0,
        duplicate_isin_count=0,
        rejected_row_count=0,
    )

    try:
        reconcile_security_masters(nse_result, bse_result)
    except ValueError as exc:
        assert "parser dates differ" in str(exc)
    else:
        raise AssertionError("Expected a ValueError for mismatched source dates")
