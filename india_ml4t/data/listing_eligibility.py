"""Derived listing records combining raw exchange data and eligibility."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

from india_ml4t.data.eligibility import (
    ListingEligibilityAssessment,
    Stage1FPolicy,
    assess_listings_eligibility,
)
from india_ml4t.data.schemas import (
    LISTING_DF_COLUMNS,
    ExchangeListingRecord,
)


@dataclass(frozen=True)
class DerivedListingEligibilityRecord:
    """Original listing plus its separate eligibility assessment."""

    listing: ExchangeListingRecord
    research_eligibility: str
    trading_eligibility: str
    reason_code: str
    detail: str
    policy_version: str
    assessment_date: date | None


DERIVED_LISTING_DF_COLUMNS = LISTING_DF_COLUMNS + (
    "research_eligibility",
    "trading_eligibility",
    "reason_code",
    "detail",
    "policy_version",
    "assessment_date",
)


def build_listing_eligibility_records(
    listings: Iterable[ExchangeListingRecord],
    policy: Stage1FPolicy | None = None,
    as_of_date: date | None = None,
) -> tuple[DerivedListingEligibilityRecord, ...]:
    """Build one derived record per listing without changing source data."""
    source_listings = tuple(listings)
    assessments: tuple[ListingEligibilityAssessment, ...] = assess_listings_eligibility(
        source_listings, policy
    )

    records = []

    for listing, assessment in zip(source_listings, assessments, strict=True):
        if listing.isin != assessment.isin or listing.exchange != assessment.exchange:
            raise ValueError("Listing and eligibility assessment identities do not match.")

        records.append(
            DerivedListingEligibilityRecord(
                listing=listing,
                research_eligibility=assessment.research_eligibility,
                trading_eligibility=assessment.trading_eligibility,
                reason_code=assessment.reason_code,
                detail=assessment.detail,
                policy_version=assessment.policy_version,
                assessment_date=as_of_date if as_of_date is not None else listing.as_of_date,
            )
        )

    return tuple(records)


def listing_eligibility_dataframe(
    records: Iterable[DerivedListingEligibilityRecord],
) -> pd.DataFrame:
    """Return a flat DataFrame with stable raw and derived column ordering."""
    rows = []

    for record in records:
        row = asdict(record.listing)
        row.update(
            {
                "research_eligibility": record.research_eligibility,
                "trading_eligibility": record.trading_eligibility,
                "reason_code": record.reason_code,
                "detail": record.detail,
                "policy_version": record.policy_version,
                "assessment_date": record.assessment_date,
            }
        )
        rows.append(row)

    if not rows:
        return pd.DataFrame(
            {column: pd.Series(dtype="object") for column in DERIVED_LISTING_DF_COLUMNS}
        )

    return pd.DataFrame(rows, columns=list(DERIVED_LISTING_DF_COLUMNS))
