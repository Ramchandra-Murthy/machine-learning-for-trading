"""Parser for BSE cash-market security master files stored in ZIP archives."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from india_ml4t.data.policy import POLICY_VERSION, PolicyBundle, ReasonCodes, classify_isin_prefix
from india_ml4t.data.schemas import (
    DuplicateIsinDiagnostic,
    ExchangeListingRecord,
    RejectedRecord,
    SecurityMasterParseResult,
    SecurityRecord,
    SymbolHistoryRecord,
)

PARSER_VERSION = "gate1c-bse-master-v0.1.0"

_ISIN_FIELD = "ISIN"
_SYMBOL_FIELD = "TckrSymb"
_INST_ID_FIELD = "FinInstrmId"


def _pick(row: dict[str, str], field: str) -> str | None:
    value = (row.get(field) or "").strip()
    return value or None


def _blank_row(row: dict[str, str]) -> bool:
    return all(not (value or "").strip() for value in row.values())


def _canonical_name(names: list[str]) -> str | None:
    values = sorted({name.strip() for name in names if name and name.strip()})
    return values[0] if values else None


def _select_member(archive: zipfile.ZipFile, member_name: str | None) -> str:
    if member_name is not None:
        if member_name not in archive.namelist():
            raise ValueError(f"BSE CSV member not found in ZIP: {member_name}")
        return member_name

    candidates = sorted(
        name
        for name in archive.namelist()
        if Path(name).name.startswith("BSE_EQ_SCRIP_") and name.lower().endswith(".csv")
    )
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one BSE_EQ_SCRIP_*.csv member; found {len(candidates)}: {candidates}"
        )
    return candidates[0]


def parse_bse_security_master(
    source_file: Path,
    as_of_date: date,
    policy_bundle: PolicyBundle | None = None,
    parser_version: str = PARSER_VERSION,
    member_name: str | None = None,
) -> SecurityMasterParseResult:
    """Parse a BSE SCRIP ZIP archive into shared typed security-master records.

    The parser preserves all valid listings and does not apply series,
    research-universe, or trading-eligibility filters. The checksum covers
    the exact uncompressed CSV member bytes.
    """
    resolved_path = Path(source_file)
    policy_version = policy_bundle.version if policy_bundle is not None else POLICY_VERSION

    with zipfile.ZipFile(resolved_path, mode="r") as archive:
        selected_member = _select_member(archive, member_name)
        member_bytes = archive.read(selected_member)

    source_checksum = hashlib.sha256(member_bytes).hexdigest()
    source_label = f"{resolved_path.name}!{selected_member}"

    text = io.TextIOWrapper(io.BytesIO(member_bytes), encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    if reader.fieldnames is None:
        raise ValueError(f"BSE CSV member has no header: {selected_member}")

    reader.fieldnames = [(header or "").strip().lstrip("\ufeff") for header in reader.fieldnames]

    total_source_rows = 0
    valid_listings: list[ExchangeListingRecord] = []
    history_records: list[SymbolHistoryRecord] = []
    rejected: list[RejectedRecord] = []

    rows_by_isin: dict[str, list[ExchangeListingRecord]] = defaultdict(list)
    names_by_isin: dict[str, list[str]] = defaultdict(list)
    categories_by_isin: dict[str, str] = {}

    for row_number, raw_row in enumerate(reader, start=1):
        row = {key: (value or "").strip() for key, value in raw_row.items() if key is not None}
        if _blank_row(row):
            continue

        total_source_rows += 1

        raw_isin = _pick(row, _ISIN_FIELD)
        raw_symbol = _pick(row, _SYMBOL_FIELD)
        raw_inst_id = _pick(row, _INST_ID_FIELD)

        if raw_isin is None:
            rejected.append(
                RejectedRecord(
                    row_number=row_number,
                    reason_code=ReasonCodes.MISSING_ISIN.code,
                    detail=ReasonCodes.MISSING_ISIN.description,
                    raw_symbol=raw_symbol,
                    raw_fin_instrm_id=raw_inst_id,
                    source_file=source_label,
                )
            )
            continue

        normalized_isin = raw_isin.upper()
        isin_category = classify_isin_prefix(normalized_isin)

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

        scty_srs = _pick(row, "SctySrs")
        fin_instrm_nm = _pick(row, "FinInstrmNm")
        fin_instrm_tp = _pick(row, "FinInstrmTp")
        sgmt = _pick(row, "Sgmt")
        del_flg = _pick(row, "DelFlg")
        listing_status = _pick(row, "Sts")
        listg_dt = _pick(row, "ListgDt")
        rmvl_dt = _pick(row, "RmvlDt")

        listing = ExchangeListingRecord(
            isin=normalized_isin,
            exchange="BSE",
            fin_instrm_id=raw_inst_id,
            tckr_symb=raw_symbol,
            scty_srs=scty_srs,
            fin_instrm_nm=fin_instrm_nm,
            fin_instrm_tp=fin_instrm_tp,
            sgmt=sgmt,
            del_flg=del_flg,
            listing_status=listing_status,
            listg_dt=listg_dt,
            rmvl_dt=rmvl_dt,
            as_of_date=as_of_date,
            source_file=source_label,
        )
        valid_listings.append(listing)
        rows_by_isin[normalized_isin].append(listing)

        if fin_instrm_nm is not None:
            names_by_isin[normalized_isin].append(fin_instrm_nm)
        categories_by_isin.setdefault(normalized_isin, isin_category)

        history_records.append(
            SymbolHistoryRecord(
                isin=normalized_isin,
                exchange="BSE",
                tckr_symb=raw_symbol,
                observed_on=as_of_date,
                scty_srs=scty_srs,
                fin_instrm_id=raw_inst_id,
                effective_from=None,
                effective_to=None,
                source_file=source_label,
            )
        )

    securities: list[SecurityRecord] = []
    duplicate_diagnostics: list[DuplicateIsinDiagnostic] = []

    for isin in sorted(rows_by_isin):
        group_rows = rows_by_isin[isin]
        securities.append(
            SecurityRecord(
                isin=isin,
                security_name=_canonical_name(names_by_isin.get(isin, [])),
                isin_category=categories_by_isin[isin],
            )
        )

        if len(group_rows) > 1:
            duplicate_diagnostics.append(
                DuplicateIsinDiagnostic(
                    isin=isin,
                    exchange="BSE",
                    record_count=len(group_rows),
                    symbols=tuple(sorted({r.tckr_symb for r in group_rows if r.tckr_symb})),
                    fin_instrm_ids=tuple(
                        sorted({r.fin_instrm_id for r in group_rows if r.fin_instrm_id})
                    ),
                    series_list=tuple(sorted({r.scty_srs for r in group_rows if r.scty_srs})),
                    reason_code=ReasonCodes.DUPLICATE_ISIN.code,
                    as_of_date=as_of_date,
                    source_file=source_label,
                )
            )

    sorted_listings = tuple(
        sorted(
            valid_listings,
            key=lambda r: (
                r.isin,
                r.tckr_symb or "",
                r.fin_instrm_id or "",
                r.scty_srs or "",
            ),
        )
    )
    sorted_history = tuple(
        sorted(
            history_records,
            key=lambda r: (
                r.isin,
                r.tckr_symb,
                r.fin_instrm_id or "",
                r.scty_srs or "",
            ),
        )
    )
    sorted_rejected = tuple(sorted(rejected, key=lambda r: r.row_number))

    return SecurityMasterParseResult(
        as_of_date=as_of_date,
        source_file=resolved_path,
        source_checksum=source_checksum,
        parser_version=parser_version,
        policy_version=policy_version,
        total_source_rows=total_source_rows,
        valid_listing_rows=len(sorted_listings),
        unique_isin_count=len(securities),
        duplicate_isin_count=len(duplicate_diagnostics),
        rejected_row_count=len(sorted_rejected),
        securities=tuple(securities),
        listings=sorted_listings,
        symbol_history=sorted_history,
        duplicate_isin_diagnostics=tuple(duplicate_diagnostics),
        rejected_records=sorted_rejected,
    )
