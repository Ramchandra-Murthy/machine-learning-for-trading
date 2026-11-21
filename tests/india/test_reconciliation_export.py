"""Tests for deterministic reconciliation CSV and Parquet exports."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from india_ml4t.data.eligibility import Stage1FPolicy
from india_ml4t.data.reconciliation_export import (
    export_reconciliation,
    reconciliation_dataframes,
)
from india_ml4t.data.schemas import (
    CrossExchangeSecurityRecord,
    DuplicateGroupReportRecord,
    ExchangeListingComparisonRecord,
    ReconciliationExceptionRecord,
    ReconciliationResult,
    ReconciliationSummary,
)

AS_OF = date(2026, 11, 18)


@pytest.fixture
def sample_result() -> ReconciliationResult:
    summary = ReconciliationSummary(
        as_of_date=AS_OF,
        nse_source_file="nse.csv",
        nse_source_checksum="nse-checksum",
        bse_source_file="bse.zip!member.csv",
        bse_source_checksum="bse-checksum",
        nse_parser_version="nse-v1",
        bse_parser_version="bse-v1",
        reconciliation_version="reconcile-v1",
        policy_version="policy-v1",
        common_isin_count=1,
        nse_only_isin_count=0,
        bse_only_isin_count=0,
        total_unique_isins=1,
        nse_valid_listings=1,
        bse_valid_listings=1,
        duplicate_group_count=1,
        exception_count=1,
    )

    return ReconciliationResult(
        cross_exchange_master=(
            CrossExchangeSecurityRecord(
                isin="INE002A01018",
                isin_category="INE_EQUITY",
                security_name="Reliance Industries Limited",
                match_category="COMMON",
                nse_listing_count=1,
                bse_listing_count=1,
                nse_symbols=("RELIANCE",),
                bse_symbols=("RELIANCE",),
                nse_series_list=("EQ",),
                bse_series_list=("A",),
                has_nse_duplicate=False,
                has_bse_duplicate=False,
                has_duplicate=False,
                as_of_date=AS_OF,
            ),
        ),
        exchange_listing_comparison=(
            ExchangeListingComparisonRecord(
                isin="INE002A01018",
                exchange="NSE",
                match_category="COMMON",
                tckr_symb="RELIANCE",
                fin_instrm_id="2885",
                scty_srs="EQ",
                fin_instrm_nm="Reliance Industries Limited",
                fin_instrm_tp=None,
                sgmt=None,
                del_flg="N",
                listing_status=None,
                listg_dt=None,
                rmvl_dt=None,
                as_of_date=AS_OF,
                source_file="nse.csv",
                prtd_to_trad="1",
                normal_market_eligibility="1",
            ),
            ExchangeListingComparisonRecord(
                isin="INE002A01018",
                exchange="BSE",
                match_category="COMMON",
                tckr_symb="RELIANCE",
                fin_instrm_id="500325",
                scty_srs="A",
                fin_instrm_nm="RELIANCE INDUSTRIES LTD.",
                fin_instrm_tp="A",
                sgmt="CM",
                del_flg=None,
                listing_status="A",
                listg_dt=None,
                rmvl_dt=None,
                as_of_date=AS_OF,
                source_file="bse.zip!member.csv",
            ),
        ),
        duplicate_groups=(
            DuplicateGroupReportRecord(
                isin="INE002A01018",
                exchange="BSE",
                isin_category="INE_EQUITY",
                duplicate_category="INE",
                record_count=2,
                symbols=("RELIANCE", "RELIANCE-A"),
                fin_instrm_ids=("500325", "500326"),
                series_list=("A", "B"),
                reason_code="DUPLICATE_ISIN",
                as_of_date=AS_OF,
                source_file="bse.zip!member.csv",
            ),
        ),
        exceptions=(
            ReconciliationExceptionRecord(
                exchange="NSE",
                row_number=10,
                reason_code="MISSING_ISIN",
                detail="ISIN is missing",
                raw_isin=None,
                raw_symbol="BADROW",
                raw_fin_instrm_id="9999",
                as_of_date=AS_OF,
                source_file="nse.csv",
            ),
        ),
        summary=summary,
    )


def test_reconciliation_dataframes_have_expected_datasets_and_rows(
    sample_result: ReconciliationResult,
) -> None:
    frames = reconciliation_dataframes(sample_result)

    assert set(frames) == {
        "cross_exchange_master",
        "exchange_listing_comparison",
        "duplicate_groups",
        "exceptions",
        "listing_eligibility",
        "summary",
    }

    assert len(frames["cross_exchange_master"]) == 1
    assert len(frames["exchange_listing_comparison"]) == 2
    assert len(frames["duplicate_groups"]) == 1
    assert len(frames["exceptions"]) == 1
    assert len(frames["listing_eligibility"]) == 2
    assert len(frames["summary"]) == 1
    assert frames["listing_eligibility"].loc[0, "trading_eligibility"] == "UNKNOWN"
    assert frames["listing_eligibility"].loc[0, "prtd_to_trad"] == "1"
    assert frames["listing_eligibility"].loc[0, "source_file"] == "bse.zip!member.csv"
    assert frames["listing_eligibility"].loc[1, "trading_eligibility"] == "ELIGIBLE"

    assert frames["cross_exchange_master"].columns.tolist()[0] == "isin"
    assert frames["exchange_listing_comparison"].columns.tolist()[0] == "isin"


def test_disabling_nse_normal_market_mapping_keeps_nse_unknown(
    sample_result: ReconciliationResult,
) -> None:
    frames = reconciliation_dataframes(
        sample_result,
        eligibility_policy=Stage1FPolicy(nse_normal_market_eligibility_mapping_verified=False),
    )

    eligibility = frames["listing_eligibility"]
    assert eligibility.loc[1, "trading_eligibility"] == "UNKNOWN"
    assert eligibility.loc[1, "prtd_to_trad"] == "1"
    assert eligibility.loc[0, "trading_eligibility"] == "UNKNOWN"
    assert eligibility.loc[0, "reason_code"] == "BSE_PERMISSION_MAPPING_UNVERIFIED"


def test_listing_eligibility_export_is_empty_with_stable_schema() -> None:
    result = ReconciliationResult(
        exchange_listing_comparison=(),
        summary=ReconciliationSummary(
            as_of_date=AS_OF,
            nse_source_file="nse.csv",
            nse_source_checksum="nse-checksum",
            bse_source_file="bse.zip!member.csv",
            bse_source_checksum="bse-checksum",
            nse_parser_version="nse-v1",
            bse_parser_version="bse-v1",
            reconciliation_version="reconcile-v1",
            policy_version="policy-v1",
            common_isin_count=0,
            nse_only_isin_count=0,
            bse_only_isin_count=0,
            total_unique_isins=0,
            nse_valid_listings=0,
            bse_valid_listings=0,
            duplicate_group_count=0,
            exception_count=0,
        ),
    )

    frame = reconciliation_dataframes(result)["listing_eligibility"]
    assert frame.empty
    assert "research_eligibility" in frame.columns
    assert "trading_eligibility" in frame.columns
    assert "prtd_to_trad" in frame.columns


def test_tuple_fields_are_serialised_as_compact_json(
    sample_result: ReconciliationResult,
) -> None:
    frames = reconciliation_dataframes(sample_result)

    symbols = frames["cross_exchange_master"].loc[0, "nse_symbols"]
    assert symbols == '["RELIANCE"]'
    assert json.loads(symbols) == ["RELIANCE"]

    duplicate_symbols = frames["duplicate_groups"].loc[0, "symbols"]
    assert json.loads(duplicate_symbols) == ["RELIANCE", "RELIANCE-A"]


def test_csv_and_parquet_exports_round_trip(
    sample_result: ReconciliationResult,
    tmp_path,
) -> None:
    exported = export_reconciliation(
        sample_result,
        tmp_path,
        formats=("csv", "parquet"),
    )

    assert len(exported) == 12

    for dataset in (
        "cross_exchange_master",
        "exchange_listing_comparison",
        "duplicate_groups",
        "exceptions",
        "listing_eligibility",
        "summary",
    ):
        csv_path = exported[f"{dataset}.csv"]
        parquet_path = exported[f"{dataset}.parquet"]

        assert csv_path.is_file()
        assert parquet_path.is_file()

        csv_frame = pd.read_csv(csv_path, dtype="string")
        parquet_frame = pd.read_parquet(parquet_path)

        expected = reconciliation_dataframes(sample_result)[dataset]

        assert csv_frame.columns.tolist() == expected.columns.tolist()
        assert parquet_frame.columns.tolist() == expected.columns.tolist()
        assert len(csv_frame) == len(expected)
        assert len(parquet_frame) == len(expected)


def test_export_rejects_unsupported_format(
    sample_result: ReconciliationResult,
    tmp_path,
) -> None:
    with pytest.raises(ValueError, match="Unsupported export formats"):
        export_reconciliation(
            sample_result,
            tmp_path,
            formats=("json",),  # type: ignore[arg-type]
        )


def test_export_rejects_missing_summary(tmp_path) -> None:
    result = ReconciliationResult(summary=None)

    with pytest.raises(ValueError, match="summary is missing"):
        export_reconciliation(result, tmp_path)


def test_reconciliation_validation_report_accepts_consistent_bundle(
    sample_result: ReconciliationResult,
) -> None:
    from india_ml4t.data.validation import validate_reconciliation_dataframes

    report = validate_reconciliation_dataframes(reconciliation_dataframes(sample_result))

    assert report.is_valid
    assert report.issues == ()
    assert report.dataset_rows["listing_eligibility"] == 2
    assert report.trading_eligibility_counts == {
        "ELIGIBLE": 1,
        "RESTRICTED": 0,
        "EXCLUDED": 0,
        "UNKNOWN": 1,
    }
    assert report.unknown_reason_counts == {
        "BSE_PERMISSION_MAPPING_UNVERIFIED": 1,
    }


def test_reconciliation_validation_detects_raw_field_drift(
    sample_result: ReconciliationResult,
) -> None:
    from india_ml4t.data.validation import validate_reconciliation_dataframes

    frames = reconciliation_dataframes(sample_result)
    frames["listing_eligibility"] = frames["listing_eligibility"].copy()
    frames["listing_eligibility"].loc[0, "source_file"] = "altered.csv"

    report = validate_reconciliation_dataframes(frames)

    assert not report.is_valid
    assert any("Raw listing fields differ" in issue for issue in report.issues)


def test_reconciliation_validation_detects_summary_count_mismatch(
    sample_result: ReconciliationResult,
) -> None:
    from india_ml4t.data.validation import validate_reconciliation_dataframes

    frames = reconciliation_dataframes(sample_result)
    frames["summary"] = frames["summary"].copy()
    frames["summary"].loc[0, "total_unique_isins"] = 99

    report = validate_reconciliation_dataframes(frames)

    assert not report.is_valid
    assert any("total_unique_isins=99" in issue for issue in report.issues)


def test_reconciliation_validation_reports_missing_datasets() -> None:
    from india_ml4t.data.validation import validate_reconciliation_dataframes

    report = validate_reconciliation_dataframes({})

    assert not report.is_valid
    assert any("Missing required datasets" in issue for issue in report.issues)
