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
from typing import Callable

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
    progress_callback: Callable[[str, float], None] | None = None,
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

    def _progress(label: str, pct: float) -> None:
        if progress_callback:
            progress_callback(label, pct)

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
    _progress("Gathering signals from 8 sources…", 0.05)
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

    _progress("Waiting for news signals (GDELT)…", 0.35)
    # ------------------------------------------------------------------
    # 2c. Join GDELT (wait up to 35s)
    # ------------------------------------------------------------------
    try:
        gdelt_signals = gdelt_future.result(timeout=35)
        signals.extend(gdelt_signals)
    except (concurrent.futures.TimeoutError, Exception) as e:
        errors.append(f"GdeltFetcher: {e}")

    _progress("Extracting claims from filing…", 0.50)
    # ------------------------------------------------------------------
    # 3. Claim extraction
    # ------------------------------------------------------------------
    # If no text was pasted, auto-fetch the most recent 10-Q/10-K from EDGAR.
    # This makes "company name only" mode actually useful — it stress-tests
    # the company's most recent earnings filing automatically.
    auto_fetched_source = None
    auto_fetched_form = None
    if not input_text and company.cik:
        result_filing = fetch_recent_filing_text(company.cik)
        if result_filing:
            input_text, auto_fetched_source, auto_fetched_form, auto_fetched_date = result_filing
            date_label = f" (filed {auto_fetched_date})" if auto_fetched_date else ""
            errors.append(f"Auto-fetched {auto_fetched_form}{date_label}: {auto_fetched_source}")

    # Private company with no pasted text — no source document to extract from.
    # Skip extraction rather than feeding a placeholder string to Claude.
    if not input_text:
        errors.append(
            "NO_SOURCE_TEXT: Company name only mode auto-fetches SEC filings, "
            "which are only available for public companies. "
            "Paste an earnings transcript, investor memo, or press release to "
            "extract and stress-test claims for this company."
        )
        claims, extraction_cost = [], 0.0
    else:
        try:
            claims, extraction_cost = extract_claims(
                text=input_text,
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

    _progress("Evaluating claim verdicts…", 0.70)
    # ------------------------------------------------------------------
    # 5. Verdict engine — one Claude call per claim, run in parallel
    # ------------------------------------------------------------------
    verdicts: dict[str, ClaimVerdictModel] = {}
    evidences: dict[str, list[Evidence]] = {}
    verdict_cost = 0.0

    def _evaluate_one(claim: Claim):
        matched_signals = evidence_map.get(claim.claim_id, [])
        return claim.claim_id, evaluate_claim(claim, matched_signals)

    completed = 0
    total_claims = len(claims)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_evaluate_one, claim): claim for claim in claims}
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            pct = 0.70 + 0.25 * (completed / total_claims) if total_claims else 0.95
            _progress(f"Evaluating claim verdicts… ({completed}/{total_claims})", pct)
            try:
                claim_id, (verdict, claim_evidences, cost) = future.result()
                verdicts[claim_id] = verdict
                evidences[claim_id] = claim_evidences
                verdict_cost += cost
            except Exception as e:
                claim = futures[future]
                errors.append(f"VerdictEngine[{claim.claim_id[:8]}]: {e}")

    total_cost += verdict_cost

    _progress("Finalizing results…", 0.95)
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
