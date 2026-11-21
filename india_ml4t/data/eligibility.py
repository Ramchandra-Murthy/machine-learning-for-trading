"""Conservative Stage 1F listing eligibility assessments.

NSE normal-market eligibility is read only from the explicitly documented
ElgbltyNrmlMkt field. The legacy PrtdToTrad field remains unmapped. BSE
trading permission remains UNKNOWN until an exchange-specific field mapping
is independently verified.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from india_ml4t.data.policy import classify_isin_prefix
from india_ml4t.data.schemas import EligibilityStatus, ExchangeListingRecord

STAGE1F_POLICY_VERSION = "stage1f-eligibility-v0.2.0"

ResearchStatus = Literal["ELIGIBLE", "EXCLUDED", "UNKNOWN"]


@dataclass(frozen=True)
class Stage1FPolicy:
    """Evidence gates for exchange-specific listing assessments.

    NSE's July 2026 pre-open FAQ (applicable from 7 September 2026) documents
    field ElgbltyNrmlMkt in NSE_CM_security_ddmmyyyy.csv.gz:
    0 = Not Eligible in Normal Market; 1 = Eligible in Normal Market.
    That explicit field is enabled by default.

    The legacy PrtdToTrad mapping is intentionally not used: the current MII
    file's observed values do not reliably express normal-market eligibility.
    Its old flag is retained only for constructor compatibility and has no
    effect on classification. BSE remains UNKNOWN pending a verified mapping.
    """

    version: str = STAGE1F_POLICY_VERSION
    nse_normal_market_eligibility_mapping_verified: bool = True
    nse_permitted_to_trade_mapping_verified: bool = False


@dataclass(frozen=True)
class ListingEligibilityAssessment:
    """Separate research inclusion and exchange normal-market assessment."""

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
    """Assess normal-market eligibility using verified exchange-specific data."""
    if listing.exchange == "NSE":
        if not policy.nse_normal_market_eligibility_mapping_verified:
            return (
                "UNKNOWN",
                "NSE_NORMAL_MARKET_MAPPING_UNVERIFIED",
                "The NSE ElgbltyNrmlMkt mapping is disabled by policy. "
                "PrtdToTrad, market status and closing-auction fields are not "
                "used as substitutes.",
            )

        value = (listing.normal_market_eligibility or "").strip()
        if value == "1":
            return (
                "ELIGIBLE",
                "NSE_NORMAL_MARKET_ELIGIBLE",
                "NSE MII Security File ElgbltyNrmlMkt=1 means eligible in the "
                "normal market. This is an exchange-file classification, not "
                "a broker-specific approval or guarantee of execution.",
            )
        if value == "0":
            return (
                "RESTRICTED",
                "NSE_NORMAL_MARKET_NOT_ELIGIBLE",
                "NSE MII Security File ElgbltyNrmlMkt=0 means not eligible in "
                "the normal market. PrtdToTrad and closing-auction fields are "
                "not used to override this value.",
            )
        return (
            "UNKNOWN",
            "NSE_NORMAL_MARKET_VALUE_UNKNOWN",
            "Missing or unrecognised NSE ElgbltyNrmlMkt value: "
            f"{value or '<blank>'}.",
        )

    if listing.exchange == "BSE":
        return (
            "UNKNOWN",
            "BSE_PERMISSION_MAPPING_UNVERIFIED",
            "No verified BSE normal-market trading-permission field mapping "
            "is enabled. Listing status alone is not treated as proof of "
            "trading permission.",
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
    """Return conservative research and normal-market assessments.

    Invalid/synthetic identities are excluded from both universes. Other
    research classifications remain UNKNOWN until instrument/series rules
    are verified. NSE normal-market eligibility uses only the documented
    ElgbltyNrmlMkt field; BSE remains UNKNOWN pending an equivalent verified
    mapping.
    """
    active_policy = policy or Stage1FPolicy()
    research_status, research_reason, research_detail = _research_assessment(listing)
    trading_status, trading_reason, trading_detail = _trading_assessment(listing, active_policy)

    # Structurally invalid or synthetic identities must never be marked
    # tradeable, even when the normal-market field says "eligible".
    if research_status == "EXCLUDED":
        trading_status = "EXCLUDED"
        reason_code, detail = research_reason, research_detail
    else:
        reason_code, detail = trading_reason, trading_detail

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
