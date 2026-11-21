"""Streamlit-facing orchestration for the existing India RP2 security-master workflow.

This module deliberately delegates parsing, reconciliation, eligibility, exports and
validation to the repository's canonical india_ml4t.data implementations.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path, PurePosixPath

import pandas as pd

from india_ml4t.data.bse_security_master import parse_bse_security_master
from india_ml4t.data.nse_security_master import parse_nse_security_master
from india_ml4t.data.reconciliation import reconcile_security_masters
from india_ml4t.data.reconciliation_export import reconciliation_dataframes
from india_ml4t.data.schemas import ReconciliationResult, SecurityMasterParseResult
from india_ml4t.data.validation import (
    ReconciliationValidationReport,
    validate_reconciliation_dataframes,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_BSE_MEMBER_BYTES = 80 * 1024 * 1024


class RP2WorkflowInputError(ValueError):
    """Raised when an uploaded RP2 source file is invalid or unsupported."""


@dataclass(frozen=True)
class RP2WorkflowResult:
    """In-memory outputs from one complete RP2 reconciliation run."""

    as_of_date: date
    nse_filename: str
    bse_filename: str
    bse_member: str
    nse: SecurityMasterParseResult
    bse: SecurityMasterParseResult
    reconciliation: ReconciliationResult
    frames: dict[str, pd.DataFrame]
    validation: ReconciliationValidationReport


def _safe_filename(filename: str) -> str:
    """Keep only the uploaded basename; never trust client-supplied path segments."""
    name = filename.replace("\\", "/").strip()
    basename = PurePosixPath(name).name
    if not basename or basename in {".", ".."}:
        raise RP2WorkflowInputError("The uploaded file must have a valid filename.")
    return basename


def discover_bse_csv_members(bse_zip_bytes: bytes) -> tuple[str, ...]:
    """Return candidate BSE_EQ_SCRIP CSV members from a BSE ZIP archive."""
    if not bse_zip_bytes:
        raise RP2WorkflowInputError("The BSE ZIP upload is empty.")
    if len(bse_zip_bytes) > MAX_UPLOAD_BYTES:
        raise RP2WorkflowInputError(
            f"The BSE ZIP exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(bse_zip_bytes), mode="r") as archive:
            candidates = tuple(
                sorted(
                    name
                    for name in archive.namelist()
                    if PurePosixPath(name).name.startswith("BSE_EQ_SCRIP_")
                    and name.lower().endswith(".csv")
                )
            )
            if not candidates:
                raise RP2WorkflowInputError(
                    "No BSE_EQ_SCRIP_*.csv member was found inside the ZIP archive."
                )
            for name in candidates:
                info = archive.getinfo(name)
                if info.flag_bits & 0x1:
                    raise RP2WorkflowInputError(
                        f"The BSE member {name!r} is encrypted and cannot be parsed."
                    )
                if info.file_size > MAX_BSE_MEMBER_BYTES:
                    raise RP2WorkflowInputError(
                        f"The BSE CSV member {name!r} exceeds the "
                        f"{MAX_BSE_MEMBER_BYTES // (1024 * 1024)} MB expanded-size limit."
                    )
            return candidates
    except zipfile.BadZipFile as exc:
        raise RP2WorkflowInputError("The BSE upload is not a valid ZIP archive.") from exc


def run_rp2_reconciliation(
    *,
    nse_filename: str,
    nse_bytes: bytes,
    bse_filename: str,
    bse_zip_bytes: bytes,
    as_of_date: date,
    bse_member: str | None = None,
) -> RP2WorkflowResult:
    """Parse uploaded NSE/BSE masters, reconcile by ISIN, assess and validate.

    The canonical parsers read from temporary files because their public inputs
    are filesystem paths. Temporary source files are removed when this function
    returns; the result retains source names, checksums and parsed records.
    The default Stage 1F policy is retained: unverified trading permissions
    remain UNKNOWN.
    """
    nse_name = _safe_filename(nse_filename)
    bse_name = _safe_filename(bse_filename)
    nse_lower = nse_name.lower()

    if not (nse_lower.endswith(".csv") or nse_lower.endswith(".csv.gz")):
        raise RP2WorkflowInputError("NSE input must be a .csv or .csv.gz file.")
    if not nse_bytes:
        raise RP2WorkflowInputError("The NSE CSV upload is empty.")
    if len(nse_bytes) > MAX_UPLOAD_BYTES:
        raise RP2WorkflowInputError(
            f"The NSE file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
        )
    if not bse_name.lower().endswith(".zip"):
        raise RP2WorkflowInputError("BSE input must be a .zip archive.")
    if len(bse_zip_bytes) > MAX_UPLOAD_BYTES:
        raise RP2WorkflowInputError(
            f"The BSE ZIP exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
        )

    candidates = discover_bse_csv_members(bse_zip_bytes)
    if bse_member is None:
        if len(candidates) != 1:
            raise RP2WorkflowInputError(
                "The BSE ZIP contains multiple matching CSV files. Select the intended "
                "BSE_EQ_SCRIP_*.csv member before running reconciliation."
            )
        selected_member = candidates[0]
    else:
        if bse_member not in candidates:
            raise RP2WorkflowInputError(
                "The selected BSE CSV member is not one of the recognised "
                "BSE_EQ_SCRIP_*.csv files in the uploaded ZIP."
            )
        selected_member = bse_member

    with tempfile.TemporaryDirectory(prefix="ml4t-rp2-") as temporary_dir:
        source_dir = Path(temporary_dir)
        nse_path = source_dir / nse_name
        bse_path = source_dir / bse_name
        nse_path.write_bytes(nse_bytes)
        bse_path.write_bytes(bse_zip_bytes)

        nse_result = replace(
            parse_nse_security_master(nse_path, as_of_date),
            source_file=Path(nse_name),
        )
        bse_result = replace(
            parse_bse_security_master(
                bse_path,
                as_of_date,
                member_name=selected_member,
            ),
            source_file=Path(bse_name),
        )
        if nse_result.valid_listing_rows == 0:
            raise RP2WorkflowInputError(
                "The NSE file produced zero valid listing rows. Check the file type and headers."
            )
        if bse_result.valid_listing_rows == 0:
            raise RP2WorkflowInputError(
                "The selected BSE CSV produced zero valid listing rows. "
                "Check that it is the intended cash-market security master."
            )
        reconciliation = reconcile_security_masters(
            nse_result,
            bse_result,
            as_of_date=as_of_date,
        )
        # Default Stage1FPolicy is intentionally conservative. In particular,
        # this workflow does not enable the unverified NSE permission mapping.
        frames = reconciliation_dataframes(reconciliation)
        validation = validate_reconciliation_dataframes(frames)

    return RP2WorkflowResult(
        as_of_date=as_of_date,
        nse_filename=nse_name,
        bse_filename=bse_name,
        bse_member=selected_member,
        nse=nse_result,
        bse=bse_result,
        reconciliation=reconciliation,
        frames=frames,
        validation=validation,
    )
