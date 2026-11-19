"""Synthetic unit tests for the BSE cash-market security master parser."""

from __future__ import annotations

import hashlib
import zipfile
from datetime import date
from pathlib import Path

from india_ml4t.data.bse_security_master import PARSER_VERSION, parse_bse_security_master
from india_ml4t.data.policy import PolicyBundle, ReasonCodes
from india_ml4t.data.schemas import SecurityMasterParseResult

AS_OF = date(2026, 11, 18)


def test_parse_bse_zip_member_checksum_status_and_groups(tmp_path: Path) -> None:
    member_name = "SCRIP/BSE_EQ_SCRIP_18112026.csv"
    csv_bytes = (
        "\n".join(
            [
                "FinInstrmId,TckrSymb,SctySrs,FinInstrmNm,ISIN,FinInstrmTp,Sgmt,DelFlg,Sts",
                "100002,ABB#,A,ABB Ltd.,ine117a01022,E,,,A",
                "100003,AEGISLOG#,B,Aegis Logistics Ltd.,INE208C01025,E,,,S",
                "100004,TESTX#,X,Test X Group,INE001A01036,E,,,A",
                "100005,TESTXT#,XT,Test XT Group,INE002A01018,E,,,A",
                "100006,TESTZ#,Z,Test Z Group,INE003A01010,E,,,S",
            ]
        )
        + "\n"
    ).encode("utf-8")

    zip_path = tmp_path / "BSE_SCRIP.zip"
    with zipfile.ZipFile(zip_path, mode="w") as archive:
        archive.writestr(member_name, csv_bytes)

    expected_member_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    bundle = PolicyBundle(version="gate1c-policy-v1", source="bse-synthetic")

    result = parse_bse_security_master(zip_path, AS_OF, policy_bundle=bundle)

    assert isinstance(result, SecurityMasterParseResult)
    assert result.as_of_date == AS_OF
    assert result.source_file == zip_path
    assert result.source_checksum == expected_member_sha256
    assert result.parser_version == PARSER_VERSION
    assert result.policy_version == "gate1c-policy-v1"
    assert result.total_source_rows == 5
    assert result.valid_listing_rows == 5
    assert result.unique_isin_count == 5
    assert result.duplicate_isin_count == 0
    assert result.rejected_row_count == 0

    series_by_isin = {row.isin: row.scty_srs for row in result.listings}
    assert series_by_isin == {
        "INE117A01022": "A",
        "INE208C01025": "B",
        "INE001A01036": "X",
        "INE002A01018": "XT",
        "INE003A01010": "Z",
    }

    abb_row = next(row for row in result.listings if row.isin == "INE117A01022")
    assert abb_row.exchange == "BSE"
    assert abb_row.tckr_symb == "ABB#"
    assert abb_row.fin_instrm_id == "100002"
    assert abb_row.listing_status == "A"
    assert abb_row.del_flg is None
    assert abb_row.sgmt is None
    assert abb_row.source_file == f"{zip_path.name}!{member_name}"

    aegis_row = next(row for row in result.listings if row.isin == "INE208C01025")
    assert aegis_row.listing_status == "S"
    assert aegis_row.del_flg is None

    for hist in result.symbol_history:
        assert hist.exchange == "BSE"
        assert hist.observed_on == AS_OF
        assert hist.effective_from is None
        assert hist.effective_to is None


def test_bse_literal_na_isin_rejected_and_duplicates_retained(tmp_path: Path) -> None:
    member_name = "SCRIP/BSE_EQ_SCRIP_18112026.csv"
    csv_bytes = (
        "\n".join(
            [
                "FinInstrmId,TckrSymb,SctySrs,FinInstrmNm,ISIN,FinInstrmTp,Sts",
                "501156,ESSRINV,B,Essar Investments Ltd.,NA,E,A",
                "501874,MACKINN,B,Mackinnon Mackenzie & Co. Ltd.,NA,E,S",
                "800020,1000GOI30,G,10% CENTRAL GOVERNMENT 2014,IN0019830010,D,S",
                "800147,10GOI2014,G,10.00% GOI 2014,IN0019830010,D,S",
            ]
        )
        + "\n"
    ).encode("utf-8")

    zip_path = tmp_path / "BSE_SCRIP.zip"
    with zipfile.ZipFile(zip_path, mode="w") as archive:
        archive.writestr(member_name, csv_bytes)

    first = parse_bse_security_master(zip_path, AS_OF)
    second = parse_bse_security_master(zip_path, AS_OF)

    assert first == second
    assert first.total_source_rows == 4
    assert first.valid_listing_rows == 2
    assert first.unique_isin_count == 1
    assert first.duplicate_isin_count == 1
    assert first.rejected_row_count == 2

    assert [(r.row_number, r.reason_code, r.raw_isin) for r in first.rejected_records] == [
        (1, ReasonCodes.MALFORMED_ISIN.code, "NA"),
        (2, ReasonCodes.MALFORMED_ISIN.code, "NA"),
    ]
    assert [d.isin for d in first.duplicate_isin_diagnostics] == ["IN0019830010"]
