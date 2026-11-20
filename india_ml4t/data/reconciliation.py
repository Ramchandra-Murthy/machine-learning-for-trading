"""Cross-exchange security master reconciliation for NSE and BSE."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from india_ml4t.data.policy import POLICY_VERSION, classify_isin_prefix
from india_ml4t.data.schemas import (
    CrossExchangeSecurityRecord,
    DuplicateCategory,
    DuplicateGroupReportRecord,
    DuplicateIsinDiagnostic,
    ExchangeListingComparisonRecord,
    ExchangeListingRecord,
    ReconciliationExceptionRecord,
    ReconciliationMatchCategory,
    ReconciliationResult,
    ReconciliationSummary,
    SecurityMasterParseResult,
)

RECONCILIATION_VERSION = "gate1d-reconcile-v0.1.0"


def _resolve_match_category(
    has_nse: bool,
    has_bse: bool,
) -> ReconciliationMatchCategory:
    """Classify an ISIN according to its exchange coverage."""
    if has_nse and has_bse:
        return "COMMON"
    if has_nse:
        return "NSE_ONLY"
    return "BSE_ONLY"


def _duplicate_category(isin_category: str) -> DuplicateCategory:
    """Map the parser's ISIN classification to a reporting category."""
    mapping: dict[str, DuplicateCategory] = {
        "DUMMY_TEST": "DUMMY",
        "INF_SCHEME": "INF",
        "INE_EQUITY": "INE",
    }
    return mapping.get(isin_category, "OTHER")


def _normalise_isin(isin: str) -> str:
    """Normalise an ISIN for matching without changing its identity."""
    return isin.strip().upper()


def _security_names(
    nse_result: SecurityMasterParseResult,
    bse_result: SecurityMasterParseResult,
) -> dict[str, str]:
    """Collect deterministic security-name metadata, preferring NSE metadata.

    This preference applies only to the descriptive name field. It does not
    select a winning listing or discard any exchange listing.
    """
    names: dict[str, str] = {}

    for result in (nse_result, bse_result):
        for security in sorted(result.securities, key=lambda item: item.isin):
            isin = _normalise_isin(security.isin)
            name = (security.security_name or "").strip()
            if name:
                names.setdefault(isin, name)

    return names


def _isin_categories(
    nse_result: SecurityMasterParseResult,
    bse_result: SecurityMasterParseResult,
) -> dict[str, str]:
    """Collect ISIN categories from parser outputs with deterministic fallback."""
    categories: dict[str, str] = {}

    for result in (bse_result, nse_result):
        for security in sorted(result.securities, key=lambda item: item.isin):
            isin = _normalise_isin(security.isin)
            category = (security.isin_category or "").strip()
            if category and category != "UNKNOWN":
                categories.setdefault(isin, category)

    return categories


def _symbols(rows: list[ExchangeListingRecord]) -> tuple[str, ...]:
    return tuple(sorted({row.tckr_symb.strip() for row in rows if row.tckr_symb}))


def _series(rows: list[ExchangeListingRecord]) -> tuple[str, ...]:
    return tuple(sorted({row.scty_srs.strip() for row in rows if row.scty_srs}))


def _listing_comparison(
    row: ExchangeListingRecord,
    match_category: ReconciliationMatchCategory,
) -> ExchangeListingComparisonRecord:
    """Convert a parser listing into the flattened comparison schema."""
    return ExchangeListingComparisonRecord(
        isin=_normalise_isin(row.isin),
        exchange=row.exchange,
        match_category=match_category,
        tckr_symb=row.tckr_symb,
        fin_instrm_id=row.fin_instrm_id,
        scty_srs=row.scty_srs,
        fin_instrm_nm=row.fin_instrm_nm,
        fin_instrm_tp=row.fin_instrm_tp,
        sgmt=row.sgmt,
        del_flg=row.del_flg,
        listing_status=row.listing_status,
        prtd_to_trad=row.prtd_to_trad,
        normal_market_status=row.normal_market_status,
        normal_market_eligibility=row.normal_market_eligibility,
        odd_lot_market_status=row.odd_lot_market_status,
        odd_lot_market_eligibility=row.odd_lot_market_eligibility,
        retail_debt_market_status=row.retail_debt_market_status,
        closing_auction_eligibility=row.closing_auction_eligibility,
        auction_market_status=row.auction_market_status,
        auction_market_eligibility=row.auction_market_eligibility,
        additional_market_1_status=row.additional_market_1_status,
        additional_market_1_eligibility=row.additional_market_1_eligibility,
        additional_market_2_status=row.additional_market_2_status,
        additional_market_2_eligibility=row.additional_market_2_eligibility,
        exchange_exclusive=row.exchange_exclusive,
        trading_permitted=row.trading_permitted,
        slbm_eligibility=row.slbm_eligibility,
        listg_dt=row.listg_dt,
        rmvl_dt=row.rmvl_dt,
        as_of_date=row.as_of_date,
        source_file=row.source_file,
    )


def _duplicate_report(
    diagnostics: tuple[DuplicateIsinDiagnostic, ...],
    *,
    exchange: str,
    categories: dict[str, str],
    fallback_date: date,
) -> list[DuplicateGroupReportRecord]:
    """Convert parser duplicate diagnostics into classified report rows."""
    reports: list[DuplicateGroupReportRecord] = []

    for diagnostic in diagnostics:
        isin = _normalise_isin(diagnostic.isin)
        isin_category = categories.get(isin) or classify_isin_prefix(isin)

        reports.append(
            DuplicateGroupReportRecord(
                isin=isin,
                exchange=exchange,  # type: ignore[arg-type]
                isin_category=isin_category,
                duplicate_category=_duplicate_category(isin_category),
                record_count=diagnostic.record_count,
                symbols=tuple(sorted(set(diagnostic.symbols))),
                fin_instrm_ids=tuple(sorted(set(diagnostic.fin_instrm_ids))),
                series_list=tuple(sorted(set(diagnostic.series_list))),
                reason_code=diagnostic.reason_code,
                as_of_date=diagnostic.as_of_date or fallback_date,
                source_file=diagnostic.source_file,
            )
        )

    return reports


def reconcile_security_masters(
    nse_result: SecurityMasterParseResult,
    bse_result: SecurityMasterParseResult,
    *,
    as_of_date: date | None = None,
    policy_version: str | None = None,
    reconciliation_version: str = RECONCILIATION_VERSION,
) -> ReconciliationResult:
    """Reconcile NSE and BSE parser outputs using normalised ISINs.

    Every valid listing is retained. Duplicate diagnostics are preserved from
    the parsers. Rejected records become explicit exceptions.

    This function does not apply trading eligibility, liquidity, price,
    volume, settlement or broker-tradability filters.
    """
    # Validate that each parser result contains listings from its own exchange.
    for expected_exchange, result in (
        ("NSE", nse_result),
        ("BSE", bse_result),
    ):
        for index, row in enumerate(result.listings, start=1):
            if row.exchange != expected_exchange:
                raise ValueError(
                    f"{expected_exchange} parser result contains listing "
                    f"assigned to exchange {row.exchange!r} "
                    f"(ISIN {row.isin!r}, listing index {index})."
                )

    resolved_date = as_of_date or nse_result.as_of_date

    if nse_result.as_of_date != bse_result.as_of_date and as_of_date is None:
        raise ValueError(
            "NSE and BSE parser dates differ. Supply an explicit as_of_date "
            "only if these source files are intentionally being reconciled."
        )

    resolved_policy = (
        policy_version or nse_result.policy_version or bse_result.policy_version or POLICY_VERSION
    )

    nse_by_isin: dict[str, list[ExchangeListingRecord]] = defaultdict(list)
    for row in nse_result.listings:
        nse_by_isin[_normalise_isin(row.isin)].append(row)

    bse_by_isin: dict[str, list[ExchangeListingRecord]] = defaultdict(list)
    for row in bse_result.listings:
        bse_by_isin[_normalise_isin(row.isin)].append(row)

    categories = _isin_categories(nse_result, bse_result)
    names = _security_names(nse_result, bse_result)

    all_isins = sorted(set(nse_by_isin) | set(bse_by_isin))

    cross_exchange_rows: list[CrossExchangeSecurityRecord] = []
    listing_rows: list[ExchangeListingComparisonRecord] = []

    common_count = 0
    nse_only_count = 0
    bse_only_count = 0

    for isin in all_isins:
        nse_rows = nse_by_isin.get(isin, [])
        bse_rows = bse_by_isin.get(isin, [])

        nse_count = len(nse_rows)
        bse_count = len(bse_rows)

        match_category = _resolve_match_category(
            has_nse=nse_count > 0,
            has_bse=bse_count > 0,
        )

        if match_category == "COMMON":
            common_count += 1
        elif match_category == "NSE_ONLY":
            nse_only_count += 1
        else:
            bse_only_count += 1

        has_nse_duplicate = nse_count > 1
        has_bse_duplicate = bse_count > 1

        isin_category = categories.get(isin) or classify_isin_prefix(isin)

        cross_exchange_rows.append(
            CrossExchangeSecurityRecord(
                isin=isin,
                isin_category=isin_category,
                security_name=names.get(isin),
                match_category=match_category,
                nse_listing_count=nse_count,
                bse_listing_count=bse_count,
                nse_symbols=_symbols(nse_rows),
                bse_symbols=_symbols(bse_rows),
                nse_series_list=_series(nse_rows),
                bse_series_list=_series(bse_rows),
                has_nse_duplicate=has_nse_duplicate,
                has_bse_duplicate=has_bse_duplicate,
                has_duplicate=has_nse_duplicate or has_bse_duplicate,
                as_of_date=resolved_date,
            )
        )

        listing_rows.extend(_listing_comparison(row, match_category) for row in nse_rows)
        listing_rows.extend(_listing_comparison(row, match_category) for row in bse_rows)

    listing_rows.sort(
        key=lambda row: (
            row.isin,
            row.exchange,
            row.tckr_symb or "",
            row.fin_instrm_id or "",
            row.scty_srs or "",
        )
    )

    duplicate_rows = _duplicate_report(
        nse_result.duplicate_isin_diagnostics,
        exchange="NSE",
        categories=categories,
        fallback_date=resolved_date,
    )
    duplicate_rows.extend(
        _duplicate_report(
            bse_result.duplicate_isin_diagnostics,
            exchange="BSE",
            categories=categories,
            fallback_date=resolved_date,
        )
    )
    duplicate_rows.sort(key=lambda row: (row.exchange, row.isin))

    exceptions: list[ReconciliationExceptionRecord] = []

    for exchange, result in (
        ("NSE", nse_result),
        ("BSE", bse_result),
    ):
        for rejected in result.rejected_records:
            exceptions.append(
                ReconciliationExceptionRecord(
                    exchange=exchange,  # type: ignore[arg-type]
                    row_number=rejected.row_number,
                    reason_code=rejected.reason_code,
                    detail=rejected.detail,
                    raw_isin=rejected.raw_isin,
                    raw_symbol=rejected.raw_symbol,
                    raw_fin_instrm_id=rejected.raw_fin_instrm_id,
                    as_of_date=result.as_of_date,
                    source_file=rejected.source_file or result.source_file.name,
                )
            )

    exceptions.sort(
        key=lambda row: (
            row.exchange,
            row.row_number,
            row.reason_code,
            row.raw_isin or "",
        )
    )

    summary = ReconciliationSummary(
        as_of_date=resolved_date,
        nse_source_file=str(nse_result.source_file),
        nse_source_checksum=nse_result.source_checksum,
        bse_source_file=str(bse_result.source_file),
        bse_source_checksum=bse_result.source_checksum,
        nse_parser_version=nse_result.parser_version,
        bse_parser_version=bse_result.parser_version,
        reconciliation_version=reconciliation_version,
        policy_version=resolved_policy,
        common_isin_count=common_count,
        nse_only_isin_count=nse_only_count,
        bse_only_isin_count=bse_only_count,
        total_unique_isins=len(all_isins),
        nse_valid_listings=len(nse_result.listings),
        bse_valid_listings=len(bse_result.listings),
        duplicate_group_count=len(duplicate_rows),
        exception_count=len(exceptions),
    )

    return ReconciliationResult(
        cross_exchange_master=tuple(cross_exchange_rows),
        exchange_listing_comparison=tuple(listing_rows),
        duplicate_groups=tuple(duplicate_rows),
        exceptions=tuple(exceptions),
        summary=summary,
    )
