"""Versioned classification rules and diagnostic reason codes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

POLICY_VERSION = "gate1-policy-v0.1.0"
_ISIN_FORMAT_PATTERN = re.compile(r"^[A-Z0-9]{12}$")


@dataclass(frozen=True)
class ReasonCode:
    code: str
    description: str


class ReasonCodes:
    MISSING_ISIN = ReasonCode("MISSING_ISIN", "Missing or blank ISIN.")
    MALFORMED_ISIN = ReasonCode(
        "MALFORMED_ISIN",
        "Fails structural 12-character format check; not full ISO 6166 validation.",
    )
    MISSING_TICKER_SYMBOL = ReasonCode("MISSING_TICKER_SYMBOL", "Missing ticker symbol.")
    MISSING_INSTRUMENT_ID = ReasonCode("MISSING_INSTRUMENT_ID", "Missing instrument ID.")
    DUPLICATE_ISIN = ReasonCode("DUPLICATE_ISIN", "Distinct ISIN appears in multiple rows.")
    DUMMY_ISIN = ReasonCode("DUMMY_ISIN", "Synthetic or test ISIN prefix.")
    INF_SCHEME_ISIN = ReasonCode("INF_SCHEME_ISIN", "Fund, scheme, or iNAV ISIN prefix.")
    NON_INE_ISIN = ReasonCode("NON_INE_ISIN", "ISIN prefix is not INE.")
    DELETED_LISTING = ReasonCode("DELETED_LISTING", "Listing marked DelFlg=Y.")
    SERIES_RESTRICTED = ReasonCode("SERIES_RESTRICTED", "Series restricted by active policy.")
    SERIES_UNCLASSIFIED = ReasonCode("SERIES_UNCLASSIFIED", "Series not mapped in active policy.")


def classify_isin_prefix(isin: str | None) -> str:
    """Structural prefix/format classification, not checksum or eligibility."""
    if isin is None or not isin.strip():
        return "MISSING"
    normalized = isin.strip().upper()
    if not _ISIN_FORMAT_PATTERN.fullmatch(normalized):
        return "MALFORMED"
    if normalized.startswith("DUMMY"):
        return "DUMMY_TEST"
    if normalized.startswith("INF"):
        return "INF_SCHEME"
    if normalized.startswith("INE"):
        return "INE_EQUITY"
    return "OTHER"


@dataclass(frozen=True)
class PolicyBundle:
    version: str = POLICY_VERSION
    effective_from: date | None = None
    effective_to: date | None = None
    source: str = "Gate 1A specification"
