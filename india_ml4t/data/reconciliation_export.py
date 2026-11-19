"""Deterministic CSV and Parquet exports for reconciliation results."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import pandas as pd

from india_ml4t.data.schemas import (
    CROSS_EXCHANGE_DF_COLUMNS,
    DUPLICATE_GROUP_DF_COLUMNS,
    EXCEPTION_DF_COLUMNS,
    LISTING_COMPARISON_DF_COLUMNS,
    ReconciliationResult,
)

ExportFormat = Literal["csv", "parquet"]

_TUPLE_COLUMNS = {
    "nse_symbols",
    "bse_symbols",
    "nse_series_list",
    "bse_series_list",
    "symbols",
    "fin_instrm_ids",
    "series_list",
}

_INTEGER_COLUMNS = {
    "nse_listing_count",
    "bse_listing_count",
    "record_count",
    "row_number",
    "common_isin_count",
    "nse_only_isin_count",
    "bse_only_isin_count",
    "total_unique_isins",
    "nse_valid_listings",
    "bse_valid_listings",
    "duplicate_group_count",
    "exception_count",
}

_BOOLEAN_COLUMNS = {
    "has_nse_duplicate",
    "has_bse_duplicate",
    "has_duplicate",
}

_DATE_COLUMNS = {"as_of_date"}

_DATASET_COLUMNS = {
    "cross_exchange_master": CROSS_EXCHANGE_DF_COLUMNS,
    "exchange_listing_comparison": LISTING_COMPARISON_DF_COLUMNS,
    "duplicate_groups": DUPLICATE_GROUP_DF_COLUMNS,
    "exceptions": EXCEPTION_DF_COLUMNS,
}


def _normalise_value(value: object, column: str) -> object:
    """Convert compound and date values into stable export values."""
    if value is None or value is pd.NA:
        return None

    if column in _TUPLE_COLUMNS:
        return json.dumps(
            list(value) if value is not None else [],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    if column in _DATE_COLUMNS and hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply stable column ordering and nullable pandas data types."""
    result = frame.copy()

    for column in result.columns:
        result[column] = result[column].map(
            lambda value, name=column: _normalise_value(value, name)
        )

        if column in _INTEGER_COLUMNS:
            result[column] = pd.array(result[column], dtype="Int64")
        elif column in _BOOLEAN_COLUMNS:
            result[column] = pd.array(result[column], dtype="boolean")
        else:
            result[column] = pd.array(result[column], dtype="string")

    return result


def reconciliation_dataframes(
    result: ReconciliationResult,
) -> dict[str, pd.DataFrame]:
    """Return the five reconciliation outputs as stable DataFrames."""
    frames = {
        "cross_exchange_master": result.to_cross_exchange_dataframe(),
        "exchange_listing_comparison": result.to_listing_comparison_dataframe(),
        "duplicate_groups": result.to_duplicate_groups_dataframe(),
        "exceptions": result.to_exceptions_dataframe(),
    }

    for name, columns in _DATASET_COLUMNS.items():
        frames[name] = frames[name].reindex(columns=list(columns))

    if result.summary is None:
        raise ValueError("ReconciliationResult.summary is missing.")

    frames["summary"] = pd.DataFrame([asdict(result.summary)])

    return {name: _prepare_frame(frame) for name, frame in frames.items()}


def export_reconciliation(
    result: ReconciliationResult,
    output_dir: str | Path,
    formats: tuple[ExportFormat, ...] = ("csv", "parquet"),
) -> dict[str, Path]:
    """Export all five reconciliation datasets in the requested formats."""
    if not formats:
        raise ValueError("At least one export format must be requested.")

    if len(set(formats)) != len(formats):
        raise ValueError("Export formats must not contain duplicates.")

    unsupported = set(formats) - {"csv", "parquet"}
    if unsupported:
        raise ValueError(f"Unsupported export formats: {sorted(unsupported)}")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    frames = reconciliation_dataframes(result)
    exported: dict[str, Path] = {}

    for dataset_name, frame in frames.items():
        for file_format in formats:
            path = destination / f"{dataset_name}.{file_format}"

            if file_format == "csv":
                frame.to_csv(
                    path,
                    index=False,
                    encoding="utf-8",
                    lineterminator="\n",
                    na_rep="",
                )
            else:
                frame.to_parquet(
                    path,
                    index=False,
                    engine="pyarrow",
                    compression="zstd",
                    version="2.6",
                    use_dictionary=False,
                    write_statistics=True,
                    data_page_version="1.0",
                )

            exported[f"{dataset_name}.{file_format}"] = path

    return exported
