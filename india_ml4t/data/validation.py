"""End-to-end consistency checks for India reconciliation exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from india_ml4t.data.schemas import LISTING_DF_COLUMNS

_REQUIRED_DATASETS = {
    "cross_exchange_master",
    "exchange_listing_comparison",
    "duplicate_groups",
    "exceptions",
    "listing_eligibility",
    "summary",
}
_ELIGIBILITY_STATUSES = ("ELIGIBLE", "RESTRICTED", "EXCLUDED", "UNKNOWN")


@dataclass(frozen=True)
class ReconciliationValidationReport:
    """Machine-readable result of validating a reconciliation export bundle."""

    is_valid: bool
    issues: tuple[str, ...]
    dataset_rows: dict[str, int]
    trading_eligibility_counts: dict[str, int]
    unknown_reason_counts: dict[str, int]


def _summary_integer(summary: pd.DataFrame, column: str) -> int | None:
    """Read a summary count while tolerating nullable/string export values."""
    if column not in summary.columns or summary.empty:
        return None
    value: Any = summary.iloc[0][column]
    if pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_reconciliation_dataframes(
    frames: dict[str, pd.DataFrame],
) -> ReconciliationValidationReport:
    """Check row-count, eligibility, and raw-field invariants across datasets.

    The input is the mapping returned by `reconciliation_dataframes`. This
    function does not mutate frames and never upgrades UNKNOWN classifications.
    """
    issues: list[str] = []
    missing = sorted(_REQUIRED_DATASETS - set(frames))
    if missing:
        issues.append(f"Missing required datasets: {', '.join(missing)}")

    dataset_rows = {name: len(frame) for name, frame in frames.items()}
    eligibility_counts = {status: 0 for status in _ELIGIBILITY_STATUSES}
    unknown_reason_counts: dict[str, int] = {}

    if missing:
        return ReconciliationValidationReport(
            is_valid=False,
            issues=tuple(issues),
            dataset_rows=dataset_rows,
            trading_eligibility_counts=eligibility_counts,
            unknown_reason_counts=unknown_reason_counts,
        )

    summary = frames["summary"]
    comparison = frames["exchange_listing_comparison"]
    eligibility = frames["listing_eligibility"]
    master = frames["cross_exchange_master"]

    if len(summary) != 1:
        issues.append(f"Expected exactly one summary row; found {len(summary)}.")

    if "trading_eligibility" not in eligibility.columns:
        issues.append("listing_eligibility is missing trading_eligibility.")
    else:
        values = eligibility["trading_eligibility"].fillna("MISSING").astype(str)
        for status in _ELIGIBILITY_STATUSES:
            eligibility_counts[status] = int(values.eq(status).sum())
        unexpected = sorted(set(values) - set(_ELIGIBILITY_STATUSES))
        if unexpected:
            issues.append(
                "Unexpected trading eligibility values: " + ", ".join(unexpected)
            )

    if "reason_code" in eligibility.columns and "trading_eligibility" in eligibility.columns:
        unknown = eligibility.loc[
            eligibility["trading_eligibility"].eq("UNKNOWN"), "reason_code"
        ].fillna("MISSING").astype(str)
        unknown_reason_counts = {
            str(reason): int(count)
            for reason, count in unknown.value_counts().sort_index().items()
        }

    if len(eligibility) != len(comparison):
        issues.append(
            "listing_eligibility row count does not match "
            "exchange_listing_comparison."
        )

    raw_columns = [column for column in LISTING_DF_COLUMNS if column in comparison.columns]
    missing_raw = sorted(set(LISTING_DF_COLUMNS) - set(eligibility.columns))
    if missing_raw:
        issues.append(
            "listing_eligibility is missing raw listing fields: "
            + ", ".join(missing_raw)
        )
    elif len(eligibility) == len(comparison) and len(raw_columns) == len(LISTING_DF_COLUMNS):
        left = comparison.loc[:, list(LISTING_DF_COLUMNS)].reset_index(drop=True)
        right = eligibility.loc[:, list(LISTING_DF_COLUMNS)].reset_index(drop=True)
        if not left.equals(right):
            issues.append(
                "Raw listing fields differ between listing_eligibility and "
                "exchange_listing_comparison."
            )

    summary_checks = (
        ("total_unique_isins", len(master), "cross_exchange_master"),
        ("nse_valid_listings", int(comparison["exchange"].eq("NSE").sum()), "NSE listings"),
        ("bse_valid_listings", int(comparison["exchange"].eq("BSE").sum()), "BSE listings"),
        ("duplicate_group_count", len(frames["duplicate_groups"]), "duplicate_groups"),
        ("exception_count", len(frames["exceptions"]), "exceptions"),
    )
    if len(summary) == 1:
        for column, actual, label in summary_checks:
            expected = _summary_integer(summary, column)
            if expected is None:
                issues.append(f"Summary count {column} is missing or invalid.")
            elif expected != actual:
                issues.append(
                    f"Summary {column}={expected} does not match {label} count {actual}."
                )

    return ReconciliationValidationReport(
        is_valid=not issues,
        issues=tuple(issues),
        dataset_rows=dataset_rows,
        trading_eligibility_counts=eligibility_counts,
        unknown_reason_counts=unknown_reason_counts,
    )
