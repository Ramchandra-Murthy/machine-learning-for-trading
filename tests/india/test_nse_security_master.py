"""Synthetic unit tests for the NSE security master parser."""

from __future__ import annotations

import gzip
import hashlib
from datetime import date
from pathlib import Path

from india_ml4t.data.nse_security_master import (
    PARSER_VERSION,
    parse_nse_security_master,
)
from india_ml4t.data.policy import PolicyBundle, ReasonCodes

AS_OF = date(2026, 11, 18)


def test_parse_gzip_csv_trimming_blank_rows_and_raw_checksum(tmp_path: Path) -> None:
    content = (
        "\n".join(
            [
                " ISIN , TckrSymb , FinInstrmId , SctySrs , FinInstrmNm , FinInstrmTp , Sgmt , DelFlg , ListgDt , RmvlDt , Xchg , Sts ",
                "   ,   ,   ,   ,   ,   ,   ,   ,   ,   ,   ,   ",
                " ine002a01018 , RELIANCE , 2885 , EQ , Reliance Industries Limited , , , N , 1995-11-29 , , , ",
                " DUMMY0000001 , TESTSYM , 999901 , EQ , Dummy Equity , , , N , , , , ",
                " INF179KC1695 , NIFTYBEES , 10576 , EQ , Nippon India ETF Nifty 50 BeES , , , N , , , , ",
                "   ,   ,   ,   ,   ,   ,   ,   ,   ,   ,   ,   ",
            ]
        )
        + "\n"
    )

    path = tmp_path / "synthetic.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(content)

    expected_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    policy = PolicyBundle(version="synthetic-policy-v1", source="synthetic-test")

    result = parse_nse_security_master(path, AS_OF, policy_bundle=policy)

    assert result.as_of_date == AS_OF
    assert result.source_file == path
    assert result.source_checksum == expected_checksum
    assert result.parser_version == PARSER_VERSION
    assert result.policy_version == "synthetic-policy-v1"

    # Blank rows do not contribute to source-row or rejection counts.
    assert result.total_source_rows == 3
    assert result.valid_listing_rows == 3
    assert result.unique_isin_count == 3
    assert result.duplicate_isin_count == 0
    assert result.rejected_row_count == 0
    assert result.rejected_records == ()

    categories = {row.isin: row.isin_category for row in result.securities}
    assert categories == {
        "DUMMY0000001": "DUMMY_TEST",
        "INE002A01018": "INE_EQUITY",
        "INF179KC1695": "INF_SCHEME",
    }

    listing = next(row for row in result.listings if row.isin == "INE002A01018")
    assert listing.exchange == "NSE"
    assert listing.tckr_symb == "RELIANCE"
    assert listing.fin_instrm_id == "2885"
    assert listing.scty_srs == "EQ"
    assert listing.fin_instrm_tp is None
    assert listing.sgmt is None
    assert listing.del_flg == "N"
    assert listing.listg_dt == "1995-11-29"
    assert listing.rmvl_dt is None

    for history in result.symbol_history:
        assert history.observed_on == AS_OF
        assert history.effective_from is None
        assert history.effective_to is None


def test_csv_rejection_precedence_and_source_row_numbers(tmp_path: Path) -> None:
    content = (
        "\n".join(
            [
                "ISIN,TckrSymb,FinInstrmId,SctySrs,FinInstrmNm,DelFlg",
                ",,,,,",
                ",,1001,EQ,No Isin Row,N",
                "BAD123,,1002,EQ,Bad Isin Row,N",
                "INE002A01018,,,EQ,Missing Symbol Row,N",
                "INE002A01018,RELIANCE,,EQ,Missing Id Row,N",
                "INE002A01018,RELIANCE,2885,EQ,Reliance Industries Limited,N",
            ]
        )
        + "\n"
    )

    path = tmp_path / "rejections.csv"
    path.write_text(content, encoding="utf-8")

    result = parse_nse_security_master(path, AS_OF)

    assert result.total_source_rows == 5
    assert result.valid_listing_rows == 1
    assert result.unique_isin_count == 1
    assert result.duplicate_isin_count == 0
    assert result.rejected_row_count == 4

    assert [(record.row_number, record.reason_code) for record in result.rejected_records] == [
        (2, ReasonCodes.MISSING_ISIN.code),
        (3, ReasonCodes.MALFORMED_ISIN.code),
        (4, ReasonCodes.MISSING_TICKER_SYMBOL.code),
        (5, ReasonCodes.MISSING_INSTRUMENT_ID.code),
    ]


def test_duplicate_isins_preserve_all_categories_and_listings(
    tmp_path: Path,
) -> None:
    content = (
        "\n".join(
            [
                "ISIN,TckrSymb,FinInstrmId,SctySrs,FinInstrmNm,DelFlg",
                "DUMMY0000001,DUMMY_A,1001,EQ,Zeta Dummy Ltd,N",
                "DUMMY0000001,DUMMY_B,1002,EQ,Alpha Dummy Ltd,N",
                "INF179KC1695,FUND_A,2001,EQ,Zeta Fund Ltd,N",
                "INF179KC1695,FUND_B,2002,EQ,Alpha Fund Ltd,N",
                "INE252A01019,PORRITSPEN,5001,EQ,Zeta Paper Mills Ltd,Y",
                "INE252A01019,VOITHPAPR,9001,EQ,Alpha Paper Mills Ltd,N",
            ]
        )
        + "\n"
    )

    path = tmp_path / "duplicates.csv"
    path.write_text(content, encoding="utf-8")

    first = parse_nse_security_master(path, AS_OF)
    second = parse_nse_security_master(path, AS_OF)

    assert first == second
    assert first.total_source_rows == 6
    assert first.valid_listing_rows == 6
    assert first.unique_isin_count == 3
    assert first.duplicate_isin_count == 3
    assert len(first.listings) == 6
    assert len(first.symbol_history) == 6
    assert len(first.duplicate_isin_diagnostics) == 3

    diagnostics = {item.isin: item for item in first.duplicate_isin_diagnostics}

    assert diagnostics["DUMMY0000001"].record_count == 2
    assert diagnostics["DUMMY0000001"].symbols == ("DUMMY_A", "DUMMY_B")

    assert diagnostics["INF179KC1695"].record_count == 2
    assert diagnostics["INF179KC1695"].symbols == ("FUND_A", "FUND_B")

    ine_diagnostic = diagnostics["INE252A01019"]
    assert ine_diagnostic.record_count == 2
    assert ine_diagnostic.symbols == ("PORRITSPEN", "VOITHPAPR")
    assert ine_diagnostic.fin_instrm_ids == ("5001", "9001")
    assert ine_diagnostic.series_list == ("EQ",)
    assert ine_diagnostic.reason_code == ReasonCodes.DUPLICATE_ISIN.code

    securities = {item.isin: item for item in first.securities}
    assert securities["INE252A01019"].security_name == "Alpha Paper Mills Ltd"

    listing_names = {(item.isin, item.tckr_symb): item.fin_instrm_nm for item in first.listings}
    assert listing_names[("INE252A01019", "PORRITSPEN")] == "Zeta Paper Mills Ltd"
    assert listing_names[("INE252A01019", "VOITHPAPR")] == "Alpha Paper Mills Ltd"

    # No duplicate listing is discarded and no historical effective dates are invented.
    for history in first.symbol_history:
        assert history.observed_on == AS_OF
        assert history.effective_from is None
        assert history.effective_to is None


def test_nse_market_fields_are_preserved_verbatim_in_listing_dataframe(tmp_path: Path) -> None:
    content = (
        "ISIN,TckrSymb,FinInstrmId,SctySrs,PrtdToTrad,SctyStsNrmlMkt,ElgbltyNrmlMkt,"
        "SctyStsOddLotMkt,ElgbltyOddLotMkt,SctyStsRETDBTMkt,ElgbltyClsgAuctnSsn,"
        "SctyStsAuctnMkt,ElgbltyAuctnMkt,SctyStsAddtlMkt1,ElgbltyAddtlMkt1,"
        "SctyStsAddtlMkt2,ElgbltyAddtlMkt2,XchgExclsv,TradgPrtd,SLBMElgblty\n"
        "INE002A01018,RELIANCE,2885,EQ,0,6,1,2,0,2,0,2,1,1,0,1,0,,,\n"
        "INE009A01021,INFY,1594,EQ,UNKNOWN,99,?,,,,,,,,,,,,,\n"
    )
    path = tmp_path / "market_fields.csv"
    path.write_text(content, encoding="utf-8")

    result = parse_nse_security_master(path, AS_OF)
    rows = {row.tckr_symb: row for row in result.listings}

    assert rows["RELIANCE"].prtd_to_trad == "0"
    assert rows["RELIANCE"].normal_market_status == "6"
    assert rows["RELIANCE"].normal_market_eligibility == "1"
    assert rows["RELIANCE"].auction_market_eligibility == "1"
    assert rows["RELIANCE"].slbm_eligibility is None
    assert rows["INFY"].prtd_to_trad == "UNKNOWN"
    assert rows["INFY"].normal_market_status == "99"
    assert rows["INFY"].normal_market_eligibility == "?"

    frame = result.to_listings_dataframe().set_index("tckr_symb")
    assert frame.loc["RELIANCE", "normal_market_status"] == "6"
    assert frame.loc["INFY", "normal_market_eligibility"] == "?"
