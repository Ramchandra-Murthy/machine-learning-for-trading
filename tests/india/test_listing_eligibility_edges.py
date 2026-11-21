from dataclasses import FrozenInstanceError
from datetime import date

import pytest

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
    }
    values.update(overrides)
    return ExchangeListingRecord(**values)


def test_policy_is_immutable():
    policy = Stage1FPolicy()
    with pytest.raises(FrozenInstanceError):
        policy.nse_normal_market_eligibility_mapping_verified = False


def test_restricted_trading_does_not_exclude_research():
    policy = Stage1FPolicy()
    result = build_listing_eligibility_records(
        [make_listing(normal_market_eligibility="0")], policy
    )[0]

    assert result.research_eligibility == "UNKNOWN"
    assert result.trading_eligibility == "RESTRICTED"
    assert result.reason_code == "NSE_NORMAL_MARKET_NOT_ELIGIBLE"


def test_verified_permission_does_not_grant_research_eligibility():
    policy = Stage1FPolicy()
    result = build_listing_eligibility_records(
        [make_listing(normal_market_eligibility="1")], policy
    )[0]

    assert result.trading_eligibility == "ELIGIBLE"
    assert result.research_eligibility == "UNKNOWN"
    assert result.reason_code == "NSE_NORMAL_MARKET_ELIGIBLE"


def test_lowercase_padded_dummy_isin_is_excluded():
    listing = make_listing(isin=" dummy0000292 ")
    result = build_listing_eligibility_records([listing])[0]

    assert result.research_eligibility == "EXCLUDED"
    assert result.trading_eligibility == "EXCLUDED"
    assert result.listing.isin == " dummy0000292 "


def test_missing_ticker_excludes_both_axes():
    result = build_listing_eligibility_records([make_listing(tckr_symb="  ")])[0]

    assert result.research_eligibility == "EXCLUDED"
    assert result.trading_eligibility == "EXCLUDED"
    assert result.reason_code == "RESEARCH_SYMBOL_MISSING"


def test_unsupported_exchange_falls_back_to_unknown():
    result = build_listing_eligibility_records([make_listing(exchange="OTHER")])[0]

    assert result.trading_eligibility == "UNKNOWN"
    assert result.reason_code == "EXCHANGE_UNSUPPORTED"


def test_batch_builder_propagates_generator_failure():
    def broken_generator():
        yield make_listing()
        raise RuntimeError("Synthetic input failure")

    with pytest.raises(RuntimeError, match="Synthetic input failure"):
        build_listing_eligibility_records(broken_generator())


def test_empty_dataframe_uses_object_dtype_for_every_column():
    frame = listing_eligibility_dataframe([])

    assert tuple(frame.columns) == DERIVED_LISTING_DF_COLUMNS
    assert all(str(dtype) == "object" for dtype in frame.dtypes)


def test_explicit_date_takes_precedence_over_listing_date():
    listing = make_listing(as_of_date=date(2026, 11, 19))
    result = build_listing_eligibility_records([listing], as_of_date=date(2026, 11, 20))[0]

    assert result.assessment_date == date(2026, 11, 20)
    assert result.listing.as_of_date == date(2026, 11, 19)
