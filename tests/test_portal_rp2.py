"""Tests for the Streamlit-facing India RP2 upload workflow."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from apps.portal.rp2_workflow import (
    RP2WorkflowInputError,
    discover_bse_csv_members,
    run_rp2_reconciliation,
)

AS_OF = date(2026, 11, 21)


def _bse_zip(*rows: str) -> bytes:
    csv_text = (
        "FinInstrmId,TckrSymb,SctySrs,FinInstrmNm,ISIN,FinInstrmTp,Sgmt,Sts\n"
        + "\n".join(rows)
        + "\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("SCRIP/BSE_EQ_SCRIP_21112026.csv", csv_text)
    return buffer.getvalue()


def _nse_csv() -> bytes:
    return (
        "ISIN,TckrSymb,FinInstrmId,SctySrs,FinInstrmNm,DelFlg,PrtdToTrad,"
        "ElgbltyNrmlMkt,SctyStsNrmlMkt\n"
        "INE002A01018,RELIANCE,2885,EQ,Reliance Industries Limited,N,0,1,6\n"
        "INE009A01021,INFY,1594,EQ,Infosys Limited,N,1,0,3\n"
    ).encode("utf-8")


def test_upload_workflow_reconciles_and_validates_all_datasets() -> None:
    bse_bytes = _bse_zip(
        "500325,RELIANCE,A,Reliance Industries Limited,INE002A01018,E,CM,A",
        "500112,HOUSING,B,Housing Development Finance Corp,INE001A01036,E,CM,A",
    )

    result = run_rp2_reconciliation(
        nse_filename="nse_master.csv",
        nse_bytes=_nse_csv(),
        bse_filename="BSE_SCRIP.zip",
        bse_zip_bytes=bse_bytes,
        as_of_date=AS_OF,
    )

    summary = result.reconciliation.summary
    assert summary is not None
    assert summary.common_isin_count == 1
    assert summary.nse_only_isin_count == 1
    assert summary.bse_only_isin_count == 1
    assert summary.total_unique_isins == 3
    assert result.validation.is_valid is True
    assert set(result.frames) == {
        "cross_exchange_master",
        "exchange_listing_comparison",
        "duplicate_groups",
        "exceptions",
        "listing_eligibility",
        "summary",
    }

    # NSE normal-market eligibility controls the NSE assessment, not PrtdToTrad.
    # BSE remains UNKNOWN because no BSE permission mapping is enabled.
    eligibility = result.frames["listing_eligibility"]
    nse = eligibility[eligibility["exchange"] == "NSE"]
    bse = eligibility[eligibility["exchange"] == "BSE"]
    assert list(nse["trading_eligibility"]) == ["ELIGIBLE", "RESTRICTED"]
    assert set(bse["trading_eligibility"]) == {"UNKNOWN"}
    assert result.nse.source_checksum
    assert result.bse.source_checksum
    assert result.bse_member == "SCRIP/BSE_EQ_SCRIP_21112026.csv"
    assert summary.nse_source_file == "nse_master.csv"
    assert summary.bse_source_file == "BSE_SCRIP.zip"


def test_bse_member_selection_is_explicit_for_multiple_matching_files() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "BSE_EQ_SCRIP_20112026.csv",
            "FinInstrmId,TckrSymb,SctySrs,FinInstrmNm,ISIN\n",
        )
        archive.writestr(
            "BSE_EQ_SCRIP_21112026.csv",
            "FinInstrmId,TckrSymb,SctySrs,FinInstrmNm,ISIN\n",
        )

    members = discover_bse_csv_members(buffer.getvalue())
    assert members == (
        "BSE_EQ_SCRIP_20112026.csv",
        "BSE_EQ_SCRIP_21112026.csv",
    )

    with pytest.raises(RP2WorkflowInputError, match="multiple matching CSV files"):
        run_rp2_reconciliation(
            nse_filename="nse.csv",
            nse_bytes=_nse_csv(),
            bse_filename="bse.zip",
            bse_zip_bytes=buffer.getvalue(),
            as_of_date=AS_OF,
        )


@pytest.mark.parametrize(
    ("nse_filename", "bse_filename", "nse_bytes", "bse_bytes", "message"),
    [
        ("nse.txt", "bse.zip", _nse_csv(), b"zip", "NSE input must"),
        ("nse.csv", "bse.csv", _nse_csv(), b"zip", "BSE input must"),
        ("nse.csv", "bse.zip", b"", b"zip", "NSE CSV upload is empty"),
        ("nse.csv", "bse.zip", _nse_csv(), b"not a zip", "not a valid ZIP"),
    ],
)
def test_upload_workflow_rejects_invalid_inputs(
    nse_filename: str,
    bse_filename: str,
    nse_bytes: bytes,
    bse_bytes: bytes,
    message: str,
) -> None:
    with pytest.raises(RP2WorkflowInputError, match=message):
        run_rp2_reconciliation(
            nse_filename=nse_filename,
            nse_bytes=nse_bytes,
            bse_filename=bse_filename,
            bse_zip_bytes=bse_bytes,
            as_of_date=AS_OF,
        )


def test_upload_workflow_rejects_path_segments_in_uploaded_names_safely() -> None:
    bse_bytes = _bse_zip(
        "500325,RELIANCE,A,Reliance Industries Limited,INE002A01018,E,CM,A"
    )
    result = run_rp2_reconciliation(
        nse_filename="../../nse_master.csv",
        nse_bytes=_nse_csv(),
        bse_filename="..\\BSE_SCRIP.zip",
        bse_zip_bytes=bse_bytes,
        as_of_date=AS_OF,
    )
    assert result.nse_filename == "nse_master.csv"
    assert result.bse_filename == "BSE_SCRIP.zip"



def test_upload_workflow_rejects_a_master_with_no_valid_listings() -> None:
    empty_nse = b"ISIN,TckrSymb,FinInstrmId,SctySrs\n"
    bse_bytes = _bse_zip(
        "500325,RELIANCE,A,Reliance Industries Limited,INE002A01018,E,CM,A"
    )
    with pytest.raises(RP2WorkflowInputError, match="zero valid listing rows"):
        run_rp2_reconciliation(
            nse_filename="empty_nse.csv",
            nse_bytes=empty_nse,
            bse_filename="BSE_SCRIP.zip",
            bse_zip_bytes=bse_bytes,
            as_of_date=AS_OF,
        )
