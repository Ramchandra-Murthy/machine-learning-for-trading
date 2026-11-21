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


def test_default_policy_uses_documented_nse_normal_market_field():
    result = assess_listing_eligibility(make_listing())

    assert result.research_eligibility == "UNKNOWN"
    assert result.trading_eligibility == "ELIGIBLE"
    assert result.reason_code == "NSE_NORMAL_MARKET_ELIGIBLE"
    assert "ElgbltyNrmlMkt=1" in result.detail
    assert "not a broker-specific approval" in result.detail
    assert result.policy_version == STAGE1F_POLICY_VERSION


def test_nse_normal_market_zero_is_restricted():
    result = assess_listing_eligibility(make_listing(normal_market_eligibility="0"))

    assert result.trading_eligibility == "RESTRICTED"
    assert result.reason_code == "NSE_NORMAL_MARKET_NOT_ELIGIBLE"


def test_missing_or_unrecognised_nse_normal_market_value_is_unknown():
    missing = assess_listing_eligibility(make_listing(normal_market_eligibility=None))
    unrecognised = assess_listing_eligibility(
        make_listing(normal_market_eligibility="9")
    )

    assert missing.trading_eligibility == "UNKNOWN"
    assert missing.reason_code == "NSE_NORMAL_MARKET_VALUE_UNKNOWN"
    assert unrecognised.trading_eligibility == "UNKNOWN"
    assert unrecognised.reason_code == "NSE_NORMAL_MARKET_VALUE_UNKNOWN"


def test_unverified_nse_normal_market_gate_can_be_disabled():
    policy = Stage1FPolicy(nse_normal_market_eligibility_mapping_verified=False)
    result = assess_listing_eligibility(make_listing(), policy)

    assert result.trading_eligibility == "UNKNOWN"
    assert result.reason_code == "NSE_NORMAL_MARKET_MAPPING_UNVERIFIED"


def test_legacy_prtd_to_trad_flag_does_not_override_normal_market_field():
    policy = Stage1FPolicy(nse_permitted_to_trade_mapping_verified=True)

    ptt_one = assess_listing_eligibility(
        make_listing(prtd_to_trad="1", normal_market_eligibility="0"), policy
    )
    ptt_zero = assess_listing_eligibility(
        make_listing(prtd_to_trad="0", normal_market_eligibility="1"), policy
    )
    ptt_only = assess_listing_eligibility(
        make_listing(prtd_to_trad="1", normal_market_eligibility=None), policy
    )

    assert ptt_one.trading_eligibility == "RESTRICTED"
    assert ptt_zero.trading_eligibility == "ELIGIBLE"
    assert ptt_only.trading_eligibility == "UNKNOWN"


def test_cas_eligibility_does_not_grant_normal_market_eligibility():
    result = assess_listing_eligibility(
        make_listing(
            prtd_to_trad=None,
            normal_market_eligibility=None,
            closing_auction_eligibility="1",
        )
    )

    assert result.trading_eligibility == "UNKNOWN"


def test_market_status_does_not_substitute_for_normal_market_eligibility():
    result = assess_listing_eligibility(
        make_listing(
            prtd_to_trad=None,
            normal_market_status="2",
            normal_market_eligibility=None,
        )
    )

    assert result.trading_eligibility == "UNKNOWN"


def test_bse_listing_status_and_normal_market_field_remain_unmapped():
    listing = make_listing(
        exchange="BSE",
        listing_status="A",
        normal_market_eligibility="1",
    )
    result = assess_listing_eligibility(listing)

    assert result.trading_eligibility == "UNKNOWN"
    assert result.reason_code == "BSE_PERMISSION_MAPPING_UNVERIFIED"


def test_dummy_isin_is_excluded_even_when_nse_normal_market_flag_is_one():
    result = assess_listing_eligibility(make_listing(isin="DUMMY0000292"))

    assert result.research_eligibility == "EXCLUDED"
    assert result.trading_eligibility == "EXCLUDED"
    assert result.reason_code == "RESEARCH_IDENTITY_INVALID"


def test_non_ine_isin_is_not_assumed_to_be_research_eligible():
    result = assess_listing_eligibility(make_listing(isin="US0378331005"))

    assert result.research_eligibility == "UNKNOWN"
    assert result.trading_eligibility == "ELIGIBLE"


def test_policy_object_is_immutable_and_versioned():
    policy = Stage1FPolicy()

    assert policy.version == STAGE1F_POLICY_VERSION
    assert policy.nse_normal_market_eligibility_mapping_verified is True
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
    listings = (
        make_listing(normal_market_eligibility=value)
        for value in ("1", "0", None)
    )
    policy = Stage1FPolicy(nse_normal_market_eligibility_mapping_verified=True)

    results = assess_listings_eligibility(listings, policy)

    assert [result.trading_eligibility for result in results] == [
        "ELIGIBLE",
        "RESTRICTED",
        "UNKNOWN",
    ]
