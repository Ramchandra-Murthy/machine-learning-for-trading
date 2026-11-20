"""Conservative Stage 1F listing eligibility assessments.

Trading permission is deliberately UNKNOWN unless the applicable exchange
field mapping has been explicitly verified and enabled in the policy.
CAS eligibility is not normal-market trading permission.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from india_ml4t.data.policy import classify_isin_prefix
from india_ml4t.data.schemas import EligibilityStatus, ExchangeListingRecord

STAGE1F_POLICY_VERSION = "stage1f-eligibility-v0.1.0"

ResearchStatus = Literal["ELIGIBLE", "EXCLUDED", "UNKNOWN"]


@dataclass(frozen=True)
class Stage1FPolicy:
    """Explicit evidence gates for exchange-specific trading mappings.

    The NSE gate defaults to False. Enabling it asserts that the current
    exchange-file mapping and code meanings have been verified outside this
    module. BSE remains UNKNOWN until a trading-permission field is verified.
    No inferred or series-only trading permission is applied.
    """

    version: str = STAGE1F_POLICY_VERSION
    nse_permitted_to_trade_mapping_verified: bool = False


@dataclass(frozen=True)
class ListingEligibilityAssessment:
    """Separate research inclusion and exchange trading-permission results."""

    isin: str
    exchange: str
    research_eligibility: ResearchStatus
    trading_eligibility: EligibilityStatus
    reason_code: str
    detail: str
    policy_version: str


def _research_assessment(
    listing: ExchangeListingRecord,
) -> tuple[ResearchStatus, str, str]:
    """Assess structural suitability for research, not trade execution."""
    isin_category = classify_isin_prefix(listing.isin)

    if isin_category in {"MISSING", "MALFORMED", "DUMMY_TEST"}:
        return (
            "EXCLUDED",
            "RESEARCH_IDENTITY_INVALID",
            f"ISIN structural category is {isin_category}.",
        )

    if not listing.tckr_symb or not listing.tckr_symb.strip():
        return (
            "EXCLUDED",
            "RESEARCH_SYMBOL_MISSING",
            "Listing has no ticker symbol.",
        )

    return (
        "UNKNOWN",
        "RESEARCH_INSTRUMENT_CLASS_UNVERIFIED",
        "Identity is structurally usable, but instrument/series classification "
        "has not been verified for research-universe inclusion.",
    )


def _trading_assessment(
    listing: ExchangeListingRecord,
    policy: Stage1FPolicy,
) -> tuple[EligibilityStatus, str, str]:
    """Apply only explicitly enabled, exchange-specific permission mappings."""
    if listing.exchange == "NSE":
        if not policy.nse_permitted_to_trade_mapping_verified:
            return (
                "UNKNOWN",
                "NSE_PERMISSION_MAPPING_UNVERIFIED",
                "Current NSE CSV mapping for PrtdToTrad has not been enabled as "
                "verified. CAS and market-status fields are not substitutes.",
            )

        value = (listing.prtd_to_trad or "").strip()
        if value == "1":
            return (
                "ELIGIBLE",
                "NSE_PERMITTED_TO_TRADE",
                "Verified NSE PermittedToTrade value indicates permission.",
            )
        if value == "0":
            return (
                "RESTRICTED",
                "NSE_NOT_PERMITTED_TO_TRADE",
                "Verified NSE PermittedToTrade value indicates no trading permission.",
            )
        if value == "2":
            return (
                "RESTRICTED",
                "NSE_BSE_EXCLUSIVE",
                "BSE-exclusive listing; not ordinary NSE trading permission.",
            )
        return (
            "UNKNOWN",
            "NSE_PERMISSION_VALUE_UNKNOWN",
            f"Missing or unrecognised PrtdToTrad value: {value or '<blank>'}.",
        )

    if listing.exchange == "BSE":
        return (
            "UNKNOWN",
            "BSE_PERMISSION_MAPPING_UNVERIFIED",
            "No verified BSE trading-permission field mapping is enabled. "
            "An active listing status is not treated as proof of trading permission.",
        )

    return (
        "UNKNOWN",
        "EXCHANGE_UNSUPPORTED",
        f"Unsupported exchange code: {listing.exchange!r}.",
    )


def assess_listing_eligibility(
    listing: ExchangeListingRecord,
    policy: Stage1FPolicy | None = None,
) -> ListingEligibilityAssessment:
    """Return conservative research and trading assessments for one listing.

    Invalid/synthetic identities are excluded from both universes. Other
    research classifications remain UNKNOWN until instrument/series rules
    are verified. Trading eligibility requires an explicitly enabled,
    exchange-specific permission mapping.
    """
    active_policy = policy or Stage1FPolicy()
    research_status, research_reason, research_detail = _research_assessment(listing)
    trading_status, trading_reason, trading_detail = _trading_assessment(listing, active_policy)

    # Structurally invalid or synthetic identities must never be marked
    # tradeable, even when an exchange permission field says "permitted".
    if research_status == "EXCLUDED":
        trading_status = "EXCLUDED"
        reason_code, detail = research_reason, research_detail
    elif trading_status != "ELIGIBLE":
        reason_code, detail = trading_reason, trading_detail
    else:
        reason_code, detail = research_reason, research_detail

    return ListingEligibilityAssessment(
        isin=listing.isin,
        exchange=listing.exchange,
        research_eligibility=research_status,
        trading_eligibility=trading_status,
        reason_code=reason_code,
        detail=detail,
        policy_version=active_policy.version,
    )


def assess_listings_eligibility(
    listings: Iterable[ExchangeListingRecord],
    policy: Stage1FPolicy | None = None,
) -> tuple[ListingEligibilityAssessment, ...]:
    """Assess multiple listings without modifying the input records.

    Results preserve input order and contain exactly one assessment
    for every listing. An empty iterable returns an empty tuple.
    """
    active_policy = policy or Stage1FPolicy()

    return tuple(assess_listing_eligibility(listing, active_policy) for listing in listings)
