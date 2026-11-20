"""Tests for conservative Stage 1F listing eligibility assessments."""

from india_ml4t.data.eligibility import (
    STAGE1F_POLICY_VERSION,
    Stage1FPolicy,
    assess_listing_eligibility,
    assess_listings_eligibility,
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


def test_default_policy_keeps_trading_permission_unknown():
    result = assess_listing_eligibility(make_listing())

    assert result.research_eligibility == "UNKNOWN"
    assert result.trading_eligibility == "UNKNOWN"
    assert result.reason_code == "NSE_PERMISSION_MAPPING_UNVERIFIED"
    assert result.policy_version == STAGE1F_POLICY_VERSION


def test_cas_eligibility_does_not_grant_normal_trading_permission():
    result = assess_listing_eligibility(
        make_listing(prtd_to_trad=None, closing_auction_eligibility="1")
    )

    assert result.trading_eligibility == "UNKNOWN"


def test_market_status_and_eligibility_do_not_override_permission_gate():
    result = assess_listing_eligibility(
        make_listing(
            prtd_to_trad=None,
            normal_market_status="2",
            normal_market_eligibility="1",
        )
    )

    assert result.trading_eligibility == "UNKNOWN"


def test_verified_nse_permission_mapping_classifies_documented_values():
    policy = Stage1FPolicy(nse_permitted_to_trade_mapping_verified=True)

    permitted = assess_listing_eligibility(make_listing(prtd_to_trad="1"), policy)
    not_permitted = assess_listing_eligibility(make_listing(prtd_to_trad="0"), policy)
    bse_exclusive = assess_listing_eligibility(make_listing(prtd_to_trad="2"), policy)

    assert permitted.trading_eligibility == "ELIGIBLE"
    assert not_permitted.trading_eligibility == "RESTRICTED"
    assert bse_exclusive.trading_eligibility == "RESTRICTED"


def test_unrecognised_nse_permission_value_falls_back_to_unknown():
    policy = Stage1FPolicy(nse_permitted_to_trade_mapping_verified=True)
    result = assess_listing_eligibility(make_listing(prtd_to_trad="9"), policy)

    assert result.trading_eligibility == "UNKNOWN"
    assert result.reason_code == "NSE_PERMISSION_VALUE_UNKNOWN"


def test_bse_listing_status_is_not_treated_as_trading_permission():
    listing = make_listing(exchange="BSE", listing_status="A")
    result = assess_listing_eligibility(listing)

    assert result.trading_eligibility == "UNKNOWN"
    assert result.reason_code == "BSE_PERMISSION_MAPPING_UNVERIFIED"


def test_dummy_isin_is_excluded_from_research_but_not_inferred_as_tradeable():
    result = assess_listing_eligibility(
        make_listing(isin="DUMMY0000292"),
        Stage1FPolicy(nse_permitted_to_trade_mapping_verified=True),
    )

    assert result.research_eligibility == "EXCLUDED"
    assert result.trading_eligibility == "EXCLUDED"


def test_non_ine_isin_is_not_assumed_to_be_research_eligible():
    result = assess_listing_eligibility(make_listing(isin="US0378331005"))

    assert result.research_eligibility == "UNKNOWN"
    assert result.trading_eligibility == "UNKNOWN"


def test_policy_object_is_immutable_and_versioned():
    policy = Stage1FPolicy()

    assert policy.version == STAGE1F_POLICY_VERSION
    assert policy.nse_permitted_to_trade_mapping_verified is False


def test_batch_assessment_preserves_order_and_cardinality():
    listings = (
        make_listing(isin="INE002A01018", exchange="NSE"),
        make_listing(isin="INE003A01024", exchange="BSE"),
        make_listing(isin="INE004A01022", exchange="NSE"),
    )

    results = assess_listings_eligibility(listings)

    assert len(results) == len(listings)
    assert [result.isin for result in results] == [listing.isin for listing in listings]
    assert [result.exchange for result in results] == [listing.exchange for listing in listings]


def test_batch_assessment_handles_empty_input():
    assert assess_listings_eligibility([]) == ()


def test_batch_assessment_accepts_generator_and_policy():
    listings = (make_listing(prtd_to_trad=value) for value in ("1", "0", None))
    policy = Stage1FPolicy(nse_permitted_to_trade_mapping_verified=True)

    results = assess_listings_eligibility(listings, policy)

    assert [result.trading_eligibility for result in results] == [
        "ELIGIBLE",
        "RESTRICTED",
        "UNKNOWN",
    ]
