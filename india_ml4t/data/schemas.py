"""Typed dataclasses and optional DataFrame views for ML4T India data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

ExchangeCode = Literal["NSE", "BSE"]
EligibilityStatus = Literal["ELIGIBLE", "RESTRICTED", "EXCLUDED", "UNKNOWN"]

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
    "listg_dt",
    "rmvl_dt",
    "as_of_date",
    "source_file",
)


def _empty_df(columns: tuple[str, ...]) -> pd.DataFrame:
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
class NSEMasterParseResult:
    """Typed output container for NSE master parsing.

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
