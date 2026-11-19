"""Typed dataclasses and optional DataFrame views for ML4T India data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

ExchangeCode = Literal["NSE", "BSE"]
EligibilityStatus = Literal["ELIGIBLE", "RESTRICTED", "EXCLUDED", "UNKNOWN"]
ReconciliationMatchCategory = Literal["COMMON", "NSE_ONLY", "BSE_ONLY"]
DuplicateCategory = Literal["DUMMY", "INF", "INE", "OTHER"]

SECURITY_DF_COLUMNS: tuple[str, ...] = (
    "isin",
    "security_name",
    "isin_category",
)

LISTING_DF_COLUMNS: tuple[str, ...] = (
    "isin",
    "exchange",
    "fin_instrm_id",
    "tckr_symb",
    "scty_srs",
    "fin_instrm_nm",
    "fin_instrm_tp",
    "sgmt",
    "del_flg",
    "listing_status",
    "listg_dt",
    "rmvl_dt",
    "as_of_date",
    "source_file",
)

CROSS_EXCHANGE_DF_COLUMNS: tuple[str, ...] = (
    "isin",
    "isin_category",
    "security_name",
    "match_category",
    "nse_listing_count",
    "bse_listing_count",
    "nse_symbols",
    "bse_symbols",
    "nse_series_list",
    "bse_series_list",
    "has_nse_duplicate",
    "has_bse_duplicate",
    "has_duplicate",
    "as_of_date",
)

LISTING_COMPARISON_DF_COLUMNS: tuple[str, ...] = (
    "isin",
    "exchange",
    "match_category",
    "tckr_symb",
    "fin_instrm_id",
    "scty_srs",
    "fin_instrm_nm",
    "fin_instrm_tp",
    "sgmt",
    "del_flg",
    "listing_status",
    "listg_dt",
    "rmvl_dt",
    "as_of_date",
    "source_file",
)

DUPLICATE_GROUP_DF_COLUMNS: tuple[str, ...] = (
    "isin",
    "exchange",
    "isin_category",
    "duplicate_category",
    "record_count",
    "symbols",
    "fin_instrm_ids",
    "series_list",
    "reason_code",
    "as_of_date",
    "source_file",
)

EXCEPTION_DF_COLUMNS: tuple[str, ...] = (
    "exchange",
    "row_number",
    "reason_code",
    "detail",
    "raw_isin",
    "raw_symbol",
    "raw_fin_instrm_id",
    "as_of_date",
    "source_file",
)


def _empty_df(columns: tuple[str, ...]) -> pd.DataFrame:
    """Return an empty DataFrame with a stable column order."""
    return pd.DataFrame({col: pd.Series(dtype="object") for col in columns})


@dataclass(frozen=True)
class SecurityRecord:
    """Canonical security identity anchored solely on ISIN."""

    isin: str
    security_name: str | None = None
    isin_category: str = "UNKNOWN"


@dataclass(frozen=True)
class ExchangeListingRecord:
    """Exchange-specific listing attributes."""

    isin: str
    exchange: ExchangeCode
    fin_instrm_id: str | None
    tckr_symb: str | None
    scty_srs: str | None
    fin_instrm_nm: str | None = None
    fin_instrm_tp: str | None = None
    sgmt: str | None = None
    del_flg: str | None = None
    listing_status: str | None = None
    listg_dt: str | None = None
    rmvl_dt: str | None = None
    as_of_date: date | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class SymbolHistoryRecord:
    """Observed symbol record with separate verified effective dates."""

    isin: str
    exchange: ExchangeCode
    tckr_symb: str
    observed_on: date
    scty_srs: str | None = None
    fin_instrm_id: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class SeriesPolicyRecord:
    """Exchange-specific series policy entry."""

    exchange: ExchangeCode
    series: str
    policy_version: str
    research_eligible: bool
    trading_eligible: bool
    settlement_restriction: str | None = None
    restriction_reason: str | None = None
    policy_source: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class UniverseSnapshotRecord:
    """Daily research or trading universe classification."""

    trade_date: date
    isin: str
    exchange: ExchangeCode
    universe_kind: Literal["RESEARCH", "TRADING"]
    eligibility: EligibilityStatus
    reason_code: str
    detail: str | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class DuplicateIsinDiagnostic:
    """A distinct ISIN appearing in multiple source rows."""

    isin: str
    exchange: ExchangeCode
    record_count: int
    symbols: tuple[str, ...]
    fin_instrm_ids: tuple[str, ...]
    series_list: tuple[str, ...]
    reason_code: str
    as_of_date: date | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class RejectedRecord:
    """Record failing field validation."""

    row_number: int
    reason_code: str
    detail: str
    raw_isin: str | None = None
    raw_symbol: str | None = None
    raw_fin_instrm_id: str | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class SecurityMasterParseResult:
    """Typed output container for NSE or BSE security master parsing.

    duplicate_isin_count counts distinct ISINs with multiple source rows,
    not excess rows.
    """

    as_of_date: date
    source_file: Path
    source_checksum: str
    parser_version: str
    policy_version: str
    total_source_rows: int
    valid_listing_rows: int
    unique_isin_count: int
    duplicate_isin_count: int
    rejected_row_count: int
    securities: tuple[SecurityRecord, ...] = field(default_factory=tuple)
    listings: tuple[ExchangeListingRecord, ...] = field(default_factory=tuple)
    symbol_history: tuple[SymbolHistoryRecord, ...] = field(default_factory=tuple)
    duplicate_isin_diagnostics: tuple[DuplicateIsinDiagnostic, ...] = field(default_factory=tuple)
    rejected_records: tuple[RejectedRecord, ...] = field(default_factory=tuple)

    def to_listings_dataframe(self) -> pd.DataFrame:
        if not self.listings:
            return _empty_df(LISTING_DF_COLUMNS)

        df = pd.DataFrame(
            [asdict(row) for row in self.listings],
            columns=list(LISTING_DF_COLUMNS),
        )
        return df.sort_values(
            ["isin", "tckr_symb", "fin_instrm_id"],
            na_position="last",
            kind="mergesort",
        ).reset_index(drop=True)

    def to_securities_dataframe(self) -> pd.DataFrame:
        if not self.securities:
            return _empty_df(SECURITY_DF_COLUMNS)

        df = pd.DataFrame(
            [asdict(row) for row in self.securities],
            columns=list(SECURITY_DF_COLUMNS),
        )
        return df.sort_values(
            ["isin"],
            na_position="last",
            kind="mergesort",
        ).reset_index(drop=True)


@dataclass(frozen=True)
class CrossExchangeSecurityRecord:
    """One reconciliation row per unique valid ISIN."""

    isin: str
    isin_category: str
    security_name: str | None
    match_category: ReconciliationMatchCategory
    nse_listing_count: int
    bse_listing_count: int
    nse_symbols: tuple[str, ...]
    bse_symbols: tuple[str, ...]
    nse_series_list: tuple[str, ...]
    bse_series_list: tuple[str, ...]
    has_nse_duplicate: bool
    has_bse_duplicate: bool
    has_duplicate: bool
    as_of_date: date


@dataclass(frozen=True)
class ExchangeListingComparisonRecord:
    """One complete exchange listing, with reconciliation classification."""

    isin: str
    exchange: ExchangeCode
    match_category: ReconciliationMatchCategory
    tckr_symb: str | None
    fin_instrm_id: str | None
    scty_srs: str | None
    fin_instrm_nm: str | None
    fin_instrm_tp: str | None
    sgmt: str | None
    del_flg: str | None
    listing_status: str | None
    listg_dt: str | None
    rmvl_dt: str | None
    as_of_date: date | None
    source_file: str | None


@dataclass(frozen=True)
class DuplicateGroupReportRecord:
    """Exchange-specific duplicate ISIN group and its diagnostic classification."""

    isin: str
    exchange: ExchangeCode
    isin_category: str
    duplicate_category: DuplicateCategory
    record_count: int
    symbols: tuple[str, ...]
    fin_instrm_ids: tuple[str, ...]
    series_list: tuple[str, ...]
    reason_code: str
    as_of_date: date | None
    source_file: str | None


@dataclass(frozen=True)
class ReconciliationExceptionRecord:
    """A rejected source record retained as a reconciliation exception."""

    exchange: ExchangeCode
    row_number: int
    reason_code: str
    detail: str
    raw_isin: str | None
    raw_symbol: str | None
    raw_fin_instrm_id: str | None
    as_of_date: date
    source_file: str | None


@dataclass(frozen=True)
class ReconciliationSummary:
    """Source provenance and reconciliation counts."""

    as_of_date: date
    nse_source_file: str
    nse_source_checksum: str
    bse_source_file: str
    bse_source_checksum: str
    nse_parser_version: str
    bse_parser_version: str
    reconciliation_version: str
    policy_version: str
    common_isin_count: int
    nse_only_isin_count: int
    bse_only_isin_count: int
    total_unique_isins: int
    nse_valid_listings: int
    bse_valid_listings: int
    duplicate_group_count: int
    exception_count: int


@dataclass(frozen=True)
class ReconciliationResult:
    """Complete deterministic cross-exchange reconciliation output."""

    cross_exchange_master: tuple[CrossExchangeSecurityRecord, ...] = field(default_factory=tuple)
    exchange_listing_comparison: tuple[ExchangeListingComparisonRecord, ...] = field(
        default_factory=tuple
    )
    duplicate_groups: tuple[DuplicateGroupReportRecord, ...] = field(default_factory=tuple)
    exceptions: tuple[ReconciliationExceptionRecord, ...] = field(default_factory=tuple)
    summary: ReconciliationSummary | None = None

    def to_cross_exchange_dataframe(self) -> pd.DataFrame:
        if not self.cross_exchange_master:
            return _empty_df(CROSS_EXCHANGE_DF_COLUMNS)

        df = pd.DataFrame(
            [asdict(row) for row in self.cross_exchange_master],
            columns=list(CROSS_EXCHANGE_DF_COLUMNS),
        )
        return df.sort_values("isin", kind="mergesort").reset_index(drop=True)

    def to_listing_comparison_dataframe(self) -> pd.DataFrame:
        if not self.exchange_listing_comparison:
            return _empty_df(LISTING_COMPARISON_DF_COLUMNS)

        df = pd.DataFrame(
            [asdict(row) for row in self.exchange_listing_comparison],
            columns=list(LISTING_COMPARISON_DF_COLUMNS),
        )
        return df.sort_values(
            ["isin", "exchange", "tckr_symb", "fin_instrm_id", "scty_srs"],
            na_position="last",
            kind="mergesort",
        ).reset_index(drop=True)

    def to_duplicate_groups_dataframe(self) -> pd.DataFrame:
        if not self.duplicate_groups:
            return _empty_df(DUPLICATE_GROUP_DF_COLUMNS)

        df = pd.DataFrame(
            [asdict(row) for row in self.duplicate_groups],
            columns=list(DUPLICATE_GROUP_DF_COLUMNS),
        )
        return df.sort_values(
            ["exchange", "isin"],
            kind="mergesort",
        ).reset_index(drop=True)

    def to_exceptions_dataframe(self) -> pd.DataFrame:
        if not self.exceptions:
            return _empty_df(EXCEPTION_DF_COLUMNS)

        df = pd.DataFrame(
            [asdict(row) for row in self.exceptions],
            columns=list(EXCEPTION_DF_COLUMNS),
        )
        return df.sort_values(
            ["exchange", "row_number", "reason_code"],
            kind="mergesort",
        ).reset_index(drop=True)


# Backward-compatible name for the original NSE parser and callers.
NSEMasterParseResult = SecurityMasterParseResult
