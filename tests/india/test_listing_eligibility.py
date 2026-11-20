from datetime import date

from india_ml4t.data.eligibility import Stage1FPolicy
from india_ml4t.data.listing_eligibility import (
    DERIVED_LISTING_DF_COLUMNS,
    build_listing_eligibility_records,
    listing_eligibility_dataframe,
)
from india_ml4t.data.schemas import ExchangeListingRecord


def make_listing(**overrides):
    values = {
        "isin": "INE002A01018",
        "exchange": "NSE",
        "fin_instrm_id": "100",
        "tckr_symb": "EXAMPLE",
        "scty_srs": "EQ",
        "prtd_to_trad": "1",
        "normal_market_status": "2",
        "normal_market_eligibility": "1",
        "closing_auction_eligibility": "1",
    }
    values.update(overrides)
    return ExchangeListingRecord(**values)


def test_builder_preserves_order_duplicates_and_raw_records():
    listings = (
        make_listing(isin="INE002A01018", tckr_symb="FIRST"),
        make_listing(isin="INE003A01024", exchange="BSE", tckr_symb="SECOND"),
        make_listing(isin="INE002A01018", tckr_symb="THIRD"),
    )

    results = build_listing_eligibility_records(listings)

    assert len(results) == len(listings)
    assert [record.listing for record in results] == list(listings)
    assert [record.listing.tckr_symb for record in results] == [
        "FIRST",
        "SECOND",
        "THIRD",
    ]


def test_builder_keeps_unverified_permission_unknown():
    listing = make_listing(prtd_to_trad="1")

    result = build_listing_eligibility_records([listing])[0]

    assert result.trading_eligibility == "UNKNOWN"
    assert result.reason_code == "NSE_PERMISSION_MAPPING_UNVERIFIED"


def test_explicit_assessment_date_takes_precedence():
    listing = make_listing(as_of_date=date(2026, 11, 19))

    result = build_listing_eligibility_records(
        [listing],
        as_of_date=date(2026, 11, 20),
    )[0]

    assert result.assessment_date == date(2026, 11, 20)
    assert result.listing.as_of_date == date(2026, 11, 19)


def test_listing_date_is_used_when_no_explicit_date_is_given():
    listing = make_listing(as_of_date=date(2026, 11, 19))

    result = build_listing_eligibility_records([listing])[0]

    assert result.assessment_date == date(2026, 11, 19)


def test_missing_dates_remain_missing():
    listing = make_listing(as_of_date=None)

    result = build_listing_eligibility_records([listing])[0]

    assert result.assessment_date is None


def test_builder_accepts_generator_and_policy():
    listings = (make_listing(prtd_to_trad=value) for value in ("1", "0", None))
    policy = Stage1FPolicy(nse_permitted_to_trade_mapping_verified=True)

    results = build_listing_eligibility_records(listings, policy)

    assert [record.trading_eligibility for record in results] == [
        "ELIGIBLE",
        "RESTRICTED",
        "UNKNOWN",
    ]


def test_dataframe_has_all_raw_and_derived_columns():
    listings = [
        make_listing(),
        make_listing(isin="INE003A01024", exchange="BSE"),
    ]

    records = build_listing_eligibility_records(listings)
    frame = listing_eligibility_dataframe(records)

    assert len(frame) == 2
    assert tuple(frame.columns) == DERIVED_LISTING_DF_COLUMNS
    assert frame.loc[0, "isin"] == listings[0].isin
    assert frame.loc[0, "research_eligibility"] == records[0].research_eligibility
    assert frame.loc[0, "trading_eligibility"] == records[0].trading_eligibility


def test_empty_input_returns_empty_records_and_stable_dataframe():
    records = build_listing_eligibility_records([])
    frame = listing_eligibility_dataframe(records)

    assert records == ()
    assert frame.empty
    assert tuple(frame.columns) == DERIVED_LISTING_DF_COLUMNS
    assert all(dtype.kind == "O" for dtype in frame.dtypes)


def test_builder_and_dataframe_do_not_mutate_raw_listing():
    listing = make_listing(
        isin="INE002A01018",
        tckr_symb="EXAMPLE",
        prtd_to_trad="1",
    )
    original_values = (
        listing.isin,
        listing.exchange,
        listing.tckr_symb,
        listing.prtd_to_trad,
        listing.as_of_date,
    )

    records = build_listing_eligibility_records([listing])
    listing_eligibility_dataframe(records)

    assert (
        listing.isin,
        listing.exchange,
        listing.tckr_symb,
        listing.prtd_to_trad,
        listing.as_of_date,
    ) == original_values
