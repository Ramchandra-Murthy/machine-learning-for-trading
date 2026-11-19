"""Parser for NSE cash-market security master files (.csv and .csv.gz)."""

from __future__ import annotations

import csv
import gzip
import hashlib
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from india_ml4t.data.policy import POLICY_VERSION, PolicyBundle, ReasonCodes, classify_isin_prefix
from india_ml4t.data.schemas import (
    DuplicateIsinDiagnostic,
    ExchangeListingRecord,
    NSEMasterParseResult,
    RejectedRecord,
    SecurityRecord,
    SymbolHistoryRecord,
)

PARSER_VERSION = "gate1b-nse-master-v0.1.0"

_ISIN_ALIASES: tuple[str, ...] = ("ISIN", "Isin", "isin")
_SYMBOL_ALIASES: tuple[str, ...] = ("TckrSymb", "TCKRSYMB", "Symbol", "SYMBOL")
_INST_ID_ALIASES: tuple[str, ...] = ("FinInstrmId", "FININSTRMID", "InstrId", "Token")
_SERIES_ALIASES: tuple[str, ...] = ("SctySrs", "SCTYSRS", "Series", "SERIES")
_NAME_ALIASES: tuple[str, ...] = ("FinInstrmNm", "FININSTRMNM", "SecurityName", "Name")
_INST_TP_ALIASES: tuple[str, ...] = ("FinInstrmTp", "FININSTRMTP")
_SGMT_ALIASES: tuple[str, ...] = ("Sgmt", "SGMT", "Segment")
_DEL_FLG_ALIASES: tuple[str, ...] = ("DelFlg", "DELFLG")
_LISTG_DT_ALIASES: tuple[str, ...] = ("ListgDt", "LISTGDT")
_RMVL_DT_ALIASES: tuple[str, ...] = ("RmvlDt", "RMVLDT")


def _compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 over the exact raw input bytes on disk."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _process_csv_stream(handle) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield (one_based_data_row_number, normalized_header_row) excluding header."""
    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        return
    normalized_headers = [(col or "").strip().lstrip("\ufeff") for col in reader.fieldnames]
    reader.fieldnames = normalized_headers
    for row_idx, raw_row in enumerate(reader, start=1):
        cleaned: dict[str, str] = {}
        for key, val in raw_row.items():
            if key is None:
                continue
            if isinstance(val, list):
                joined = ",".join(str(item or "").strip() for item in val)
                cleaned[key] = joined.strip()
            else:
                cleaned[key] = (val or "").strip()
        yield row_idx, cleaned


def _iter_csv_rows(source_file: Path) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield (one_based_data_row_number, normalized_header_row) excluding header."""
    if source_file.suffix.lower() == ".gz":
        with gzip.open(source_file, mode="rt", encoding="utf-8-sig", newline="") as handle:
            yield from _process_csv_stream(handle)
    else:
        with source_file.open(mode="r", encoding="utf-8-sig", newline="") as handle:
            yield from _process_csv_stream(handle)


def _pick_field(row: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    """Return first non-empty trimmed value across candidate column names."""
    for alias in aliases:
        if alias in row:
            val = (row[alias] or "").strip()
            if val != "":
                return val
    return None


def _is_completely_blank_row(row: dict[str, str]) -> bool:
    """Return True when every field in the source row is empty after stripping."""
    return all((val or "").strip() == "" for val in row.values())


def _canonical_security_name(names: list[str]) -> str | None:
    """Deterministic tie-breaker when multiple security names exist for one ISIN.

    Selects the lexicographically smallest non-empty name rather than relying
    on source row ordering or instrument IDs.
    """
    non_empty = sorted({n.strip() for n in names if n and n.strip()})
    return non_empty[0] if non_empty else None


def parse_nse_security_master(
    source_file: Path,
    as_of_date: date,
    policy_bundle: PolicyBundle | None = None,
    parser_version: str = PARSER_VERSION,
) -> NSEMasterParseResult:
    """Parse an NSE security master (.csv or .csv.gz) into typed records.

    PolicyBundle supplies policy-version metadata only at this stage and does
    not filter or decide trading eligibility.
    """
    resolved_path = Path(source_file)
    policy_version = policy_bundle.version if policy_bundle is not None else POLICY_VERSION
    source_checksum = _compute_file_sha256(resolved_path)
    source_label = resolved_path.name

    total_source_rows = 0
    valid_listings: list[ExchangeListingRecord] = []
    history_records: list[SymbolHistoryRecord] = []
    rejected: list[RejectedRecord] = []

    rows_by_isin: dict[str, list[ExchangeListingRecord]] = defaultdict(list)
    names_by_isin: dict[str, list[str]] = defaultdict(list)
    categories_by_isin: dict[str, str] = {}

    for row_number, row in _iter_csv_rows(resolved_path):
        # Completely blank rows are excluded from data-row counts and rejections.
        if _is_completely_blank_row(row):
            continue

        total_source_rows += 1

        raw_isin = _pick_field(row, _ISIN_ALIASES)
        raw_symbol = _pick_field(row, _SYMBOL_ALIASES)
        raw_inst_id = _pick_field(row, _INST_ID_ALIASES)

        # Precedence 1: MISSING_ISIN
        if raw_isin is None:
            rejected.append(
                RejectedRecord(
                    row_number=row_number,
                    reason_code=ReasonCodes.MISSING_ISIN.code,
                    detail=ReasonCodes.MISSING_ISIN.description,
                    raw_isin=None,
                    raw_symbol=raw_symbol,
                    raw_fin_instrm_id=raw_inst_id,
                    source_file=source_label,
                )
            )
            continue

        normalized_isin = raw_isin.upper()
        isin_category = classify_isin_prefix(normalized_isin)

        # Precedence 2: MALFORMED_ISIN
        if isin_category == "MALFORMED":
            rejected.append(
                RejectedRecord(
                    row_number=row_number,
                    reason_code=ReasonCodes.MALFORMED_ISIN.code,
                    detail=ReasonCodes.MALFORMED_ISIN.description,
                    raw_isin=raw_isin,
                    raw_symbol=raw_symbol,
                    raw_fin_instrm_id=raw_inst_id,
                    source_file=source_label,
                )
            )
            continue

        # Precedence 3: MISSING_TICKER_SYMBOL
        if raw_symbol is None:
            rejected.append(
                RejectedRecord(
                    row_number=row_number,
                    reason_code=ReasonCodes.MISSING_TICKER_SYMBOL.code,
                    detail=ReasonCodes.MISSING_TICKER_SYMBOL.description,
                    raw_isin=normalized_isin,
                    raw_symbol=None,
                    raw_fin_instrm_id=raw_inst_id,
                    source_file=source_label,
                )
            )
            continue

        # Precedence 4: MISSING_INSTRUMENT_ID
        if raw_inst_id is None:
            rejected.append(
                RejectedRecord(
                    row_number=row_number,
                    reason_code=ReasonCodes.MISSING_INSTRUMENT_ID.code,
                    detail=ReasonCodes.MISSING_INSTRUMENT_ID.description,
                    raw_isin=normalized_isin,
                    raw_symbol=raw_symbol,
                    raw_fin_instrm_id=None,
                    source_file=source_label,
                )
            )
            continue

        scty_srs = _pick_field(row, _SERIES_ALIASES)
        fin_instrm_nm = _pick_field(row, _NAME_ALIASES)
        fin_instrm_tp = _pick_field(row, _INST_TP_ALIASES)
        sgmt = _pick_field(row, _SGMT_ALIASES)
        del_flg = _pick_field(row, _DEL_FLG_ALIASES)
        listg_dt = _pick_field(row, _LISTG_DT_ALIASES)
        rmvl_dt = _pick_field(row, _RMVL_DT_ALIASES)

        listing = ExchangeListingRecord(
            isin=normalized_isin,
            exchange="NSE",
            fin_instrm_id=raw_inst_id,
            tckr_symb=raw_symbol,
            scty_srs=scty_srs,
            fin_instrm_nm=fin_instrm_nm,
            fin_instrm_tp=fin_instrm_tp,
            sgmt=sgmt,
            del_flg=del_flg,
            listg_dt=listg_dt,
            rmvl_dt=rmvl_dt,
            as_of_date=as_of_date,
            source_file=source_label,
        )
        valid_listings.append(listing)
        rows_by_isin[normalized_isin].append(listing)

        if fin_instrm_nm is not None:
            names_by_isin[normalized_isin].append(fin_instrm_nm)
        if normalized_isin not in categories_by_isin:
            categories_by_isin[normalized_isin] = isin_category

        # Effective dates are never fabricated; both remain None unless verified.
        history_records.append(
            SymbolHistoryRecord(
                isin=normalized_isin,
                exchange="NSE",
                tckr_symb=raw_symbol,
                observed_on=as_of_date,
                scty_srs=scty_srs,
                fin_instrm_id=raw_inst_id,
                effective_from=None,
                effective_to=None,
                source_file=source_label,
            )
        )

    sorted_isins = sorted(rows_by_isin.keys())
    securities: list[SecurityRecord] = []
    duplicate_diagnostics: list[DuplicateIsinDiagnostic] = []

    for isin in sorted_isins:
        group_rows = rows_by_isin[isin]
        sec_name = _canonical_security_name(names_by_isin.get(isin, []))
        securities.append(
            SecurityRecord(
                isin=isin,
                security_name=sec_name,
                isin_category=categories_by_isin[isin],
            )
        )
        if len(group_rows) > 1:
            symbols = tuple(sorted({r.tckr_symb for r in group_rows if r.tckr_symb}))
            inst_ids = tuple(sorted({r.fin_instrm_id for r in group_rows if r.fin_instrm_id}))
            series_vals = tuple(sorted({r.scty_srs for r in group_rows if r.scty_srs}))
            duplicate_diagnostics.append(
                DuplicateIsinDiagnostic(
                    isin=isin,
                    exchange="NSE",
                    record_count=len(group_rows),
                    symbols=symbols,
                    fin_instrm_ids=inst_ids,
                    series_list=series_vals,
                    reason_code=ReasonCodes.DUPLICATE_ISIN.code,
                    as_of_date=as_of_date,
                    source_file=source_label,
                )
            )

    sorted_listings = tuple(
        sorted(
            valid_listings,
            key=lambda r: (r.isin, r.tckr_symb or "", r.fin_instrm_id or "", r.scty_srs or ""),
        )
    )
    sorted_history = tuple(
        sorted(
            history_records,
            key=lambda r: (r.isin, r.tckr_symb, r.fin_instrm_id or "", r.scty_srs or ""),
        )
    )
    sorted_rejected = tuple(sorted(rejected, key=lambda r: r.row_number))

    return NSEMasterParseResult(
        as_of_date=as_of_date,
        source_file=resolved_path,
        source_checksum=source_checksum,
        parser_version=parser_version,
        policy_version=policy_version,
        total_source_rows=total_source_rows,
        valid_listing_rows=len(sorted_listings),
        unique_isin_count=len(sorted_isins),
        duplicate_isin_count=len(duplicate_diagnostics),
        rejected_row_count=len(sorted_rejected),
        securities=tuple(securities),
        listings=sorted_listings,
        symbol_history=sorted_history,
        duplicate_isin_diagnostics=tuple(duplicate_diagnostics),
        rejected_records=sorted_rejected,
    )
