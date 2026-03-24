"""
Pipeline orchestrator — Step 6a.

Coordinates the full analysis pipeline:
  1. Pre-run spend check
  2. Signal fetching (synchronous fetchers in parallel, GDELT async in background)
  3. Claim extraction (Claude call 1)
  4. Evidence mapping (static, no API)
  5. Verdict engine (Claude call per claim)
  6. GDELT signal join (after primary fetchers complete)
  7. Spend recording

Returns an AnalysisResult containing everything the UI needs.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fetchers.edgar import fetch_recent_filing_text
from fetchers.adzuna import AdzunaFetcher
from fetchers.appstore import AppStoreFetcher
from fetchers.edgar import EdgarFetcher
from fetchers.gdelt import fetch_gdelt
from fetchers.github import GitHubFetcher
from fetchers.google_trends import GoogleTrendsFetcher
from fetchers.wappalyzer import WappalyzerFetcher
from fetchers.wayback import WaybackFetcher
from pipeline.claim_extractor import extract_claims
from pipeline.evidence_mapper import CLAIM_SIGNAL_MAP, coverage_summary, map_evidence
from pipeline.verdict_engine import evaluate_claim
from schema.enums import AnalysisStatus, InputType
from schema.models import Analysis, Claim, ClaimVerdictModel, Company, Evidence, Signal
from spend.tracker import SpendTracker

_SYNC_FETCHERS = [
    EdgarFetcher(),
    GoogleTrendsFetcher(),
    GitHubFetcher(),
    WaybackFetcher(),
    AppStoreFetcher(),
    AdzunaFetcher(),
    WappalyzerFetcher(),
]


@dataclass
class AnalysisResult:
    analysis: Analysis
    claims: list[Claim]
    verdicts: dict[str, ClaimVerdictModel]   # claim_id → verdict
    evidences: dict[str, list[Evidence]]      # claim_id → per-signal evidence
    signals: list[Signal]
    coverage: dict
    errors: list[str] = field(default_factory=list)


def run_analysis(
    company: Company,
    input_text: str | None,
    input_type: InputType,
    competitors: list[str] | None = None,
    spend_tracker: SpendTracker | None = None,
) -> AnalysisResult:
    """
    Run the full narrative stress test pipeline.

    Args:
        company: Company entity (must have entity_id, name, domain; CIK for public cos)
        input_text: Raw text for paste modes; None triggers company-name-only mode
        input_type: One of InputType enum values
        competitors: Optional list of competitor names for Google Trends comparison
        spend_tracker: SpendTracker instance; created fresh if not provided

    Returns:
        AnalysisResult with all claims, verdicts, signals, and spend metadata
    """
    tracker = spend_tracker or SpendTracker()
    errors: list[str] = []

    # ------------------------------------------------------------------
    # 1. Pre-run spend check (rough estimate: $0.10 per analysis)
    # ------------------------------------------------------------------
    ESTIMATED_COST = 0.10
    if tracker.would_exceed(ESTIMATED_COST):
        status = tracker.status()
        raise RuntimeError(
            f"Daily spend limit reached (${status['spent_usd']:.2f} / "
            f"${status['limit_usd']:.2f}). Resets tomorrow."
        )

    analysis = Analysis(
        entity_id=company.entity_id,
        input_type=input_type,
        input_text=input_text,
        run_at=datetime.now(timezone.utc),
        status=AnalysisStatus.partial,
    )

    # ------------------------------------------------------------------
    # 2a. Fire GDELT in background thread (14s+ latency — don't block)
    # ------------------------------------------------------------------
    gdelt_future: concurrent.futures.Future = concurrent.futures.ThreadPoolExecutor(
        max_workers=1
    ).submit(_run_gdelt_sync, company)

    # ------------------------------------------------------------------
    # 2b. Run synchronous fetchers
    # ------------------------------------------------------------------
    signals: list[Signal] = []
    for fetcher in _SYNC_FETCHERS:
        try:
            fetcher_name = type(fetcher).__name__
            fetched = (
                fetcher.fetch(company, competitors)  # GoogleTrendsFetcher accepts competitors
                if isinstance(fetcher, GoogleTrendsFetcher)
                else fetcher.fetch(company)
            )
            signals.extend(fetched)
        except Exception as e:
            errors.append(f"{type(fetcher).__name__}: {e}")

    # ------------------------------------------------------------------
    # 2c. Join GDELT (wait up to 35s)
    # ------------------------------------------------------------------
    try:
        gdelt_signals = gdelt_future.result(timeout=35)
        signals.extend(gdelt_signals)
    except (concurrent.futures.TimeoutError, Exception) as e:
        errors.append(f"GdeltFetcher: {e}")

    # ------------------------------------------------------------------
    # 3. Claim extraction
    # ------------------------------------------------------------------
    # If no text was pasted, auto-fetch the most recent 8-K from EDGAR.
    # This makes "company name only" mode actually useful — it stress-tests
    # the company's most recent earnings filing automatically.
    auto_fetched_source = None
    auto_fetched_form = None
    if not input_text and company.cik:
        result_filing = fetch_recent_filing_text(company.cik)
        if result_filing:
            input_text, auto_fetched_source, auto_fetched_form = result_filing
            errors.append(f"Auto-fetched {auto_fetched_form}: {auto_fetched_source}")

    text_for_extraction = input_text or f"{company.name} is a company."
    try:
        claims, extraction_cost = extract_claims(
            text=text_for_extraction,
            analysis_id=analysis.analysis_id,
            entity_id=company.entity_id,
            company_name=company.name,
        )
    except Exception as e:
        errors.append(f"ClaimExtractor: {e}")
        claims, extraction_cost = [], 0.0

    total_cost = extraction_cost

    # ------------------------------------------------------------------
    # 4. Evidence mapping
    # ------------------------------------------------------------------
    evidence_map = map_evidence(claims, signals)
    coverage = coverage_summary(evidence_map)

    # ------------------------------------------------------------------
    # 5. Verdict engine — one call per claim
    # ------------------------------------------------------------------
    verdicts: dict[str, ClaimVerdictModel] = {}
    evidences: dict[str, list[Evidence]] = {}
    verdict_cost = 0.0

    for claim in claims:
        matched_signals = evidence_map.get(claim.claim_id, [])
        try:
            verdict, claim_evidences, cost = evaluate_claim(claim, matched_signals)
            verdicts[claim.claim_id] = verdict
            evidences[claim.claim_id] = claim_evidences
            verdict_cost += cost
        except Exception as e:
            errors.append(f"VerdictEngine[{claim.claim_id[:8]}]: {e}")

    total_cost += verdict_cost

    # ------------------------------------------------------------------
    # 6. Finalise Analysis record
    # ------------------------------------------------------------------
    tested_count = sum(
        1 for v in verdicts.values()
        if v.verdict.value != "not_testable"
    )
    analysis.cost_usd = round(total_cost, 6)
    analysis.claim_count = len(claims)
    analysis.tested_count = tested_count
    analysis.status = AnalysisStatus.complete if claims else AnalysisStatus.partial

    # ------------------------------------------------------------------
    # 7. Record spend
    # ------------------------------------------------------------------
    tracker.record(
        analysis_id=analysis.analysis_id,
        cost_usd=total_cost,
        note=f"{len(claims)} claims, {tested_count} tested",
    )

    return AnalysisResult(
        analysis=analysis,
        claims=claims,
        verdicts=verdicts,
        evidences=evidences,
        signals=signals,
        coverage=coverage,
        errors=errors,
    )


def _run_gdelt_sync(company: Company) -> list[Signal]:
    """Run the async GDELT fetcher in a sync context (for ThreadPoolExecutor)."""
    return asyncio.run(fetch_gdelt(company))
