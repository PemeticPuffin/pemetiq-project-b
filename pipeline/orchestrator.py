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

# Overall wall-clock bound on the signal-gathering phase. Fetchers run
# concurrently, so this caps the phase at the slowest fetcher we're willing to
# wait for — and protects against ones with no internal timeout (pytrends) or a
# long one. Anything not done by the deadline is dropped; partial signals are
# fine and the UI discloses which sources returned data. Sized to roughly match
# the parallel claim-extraction track so neither dominates the critical path.
_SIGNAL_PHASE_DEADLINE = 25


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
    pdf_bytes: bytes | None = None,
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
    # 2. Parallel phase — signal fetching AND claim extraction run at once.
    #
    # Claim extraction (including any EDGAR filing auto-fetch) is independent
    # of the signal fetchers: extraction turns source text into claims, while
    # the fetchers gather signals. Evidence mapping below is the join point
    # that needs both. Overlapping them hides the ~15-20s extraction latency
    # entirely under the signal-fetch window instead of paying it serially.
    # ------------------------------------------------------------------
    _progress("Gathering signals and extracting claims…", 0.05)

    # 2a. Fire GDELT (14s+ latency) and claim extraction in their own threads.
    gdelt_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    gdelt_future = gdelt_pool.submit(_run_gdelt_sync, company)

    claim_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    claim_future = claim_pool.submit(
        _extract_claims_phase, company, input_text, pdf_bytes, analysis.analysis_id
    )

    # 2b. Run synchronous fetchers concurrently on this thread's pool.
    def _run_fetcher(fetcher) -> tuple[list[Signal], list[str]]:
        try:
            fetched = (
                fetcher.fetch(company, competitors)
                if isinstance(fetcher, GoogleTrendsFetcher)
                else fetcher.fetch(company)
            )
            return fetched, []
        except Exception as e:
            return [], [f"{type(fetcher).__name__}: {e}"]

    signals: list[Signal] = []
    fetcher_pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(_SYNC_FETCHERS))
    future_to_name = {
        fetcher_pool.submit(_run_fetcher, f): type(f).__name__ for f in _SYNC_FETCHERS
    }
    try:
        for future in concurrent.futures.as_completed(
            future_to_name, timeout=_SIGNAL_PHASE_DEADLINE
        ):
            fetched, errs = future.result()
            signals.extend(fetched)
            errors.extend(errs)
    except concurrent.futures.TimeoutError:
        for future, name in future_to_name.items():
            if not future.done():
                errors.append(
                    f"{name}: dropped — exceeded {_SIGNAL_PHASE_DEADLINE}s signal deadline"
                )
    finally:
        fetcher_pool.shutdown(wait=False)

    # 2c. Join GDELT. Its own 20s aiohttp timeout guarantees the thread
    # completes; this bounds the join itself against the same phase deadline.
    try:
        gdelt_signals = gdelt_future.result(timeout=_SIGNAL_PHASE_DEADLINE)
        signals.extend(gdelt_signals)
    except (concurrent.futures.TimeoutError, Exception) as e:
        errors.append(f"GdeltFetcher: {e}")
    finally:
        gdelt_pool.shutdown(wait=False)

    # 2d. Join claim extraction (already running — usually done by now).
    _progress("Mapping evidence to claims…", 0.55)
    try:
        claims, extraction_cost, claim_errors = claim_future.result()
        errors.extend(claim_errors)
    except Exception as e:
        errors.append(f"ClaimExtractor: {e}")
        claims, extraction_cost = [], 0.0
    finally:
        claim_pool.shutdown(wait=False)

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
    # One Claude call per claim, all fired concurrently. The claim cap is 20,
    # so a 20-wide pool evaluates every claim in a single round (~7s) rather
    # than batching — this keeps the verdict phase flat as claim count grows.
    verdict_workers = max(1, min(total_claims, 20))
    with concurrent.futures.ThreadPoolExecutor(max_workers=verdict_workers) as pool:
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


def _extract_claims_phase(
    company: Company,
    input_text: str | None,
    pdf_bytes: bytes | None,
    analysis_id: str,
) -> tuple[list[Claim], float, list[str]]:
    """Resolve source text and extract claims. Runs concurrently with fetchers.

    For company-name-only mode this first auto-fetches the most recent 10-Q/10-K
    from EDGAR, then extracts claims from it — so the entire fetch-then-extract
    sub-chain overlaps the signal-fetch window rather than running after it.

    Returns (claims, extraction_cost, errors). Never raises — failures are
    captured in the returned errors list so a bad extraction can't abort the run.
    """
    errors: list[str] = []

    # No pasted text → auto-fetch the latest filing (public companies only).
    if not input_text and company.cik:
        result_filing = fetch_recent_filing_text(company.cik)
        if result_filing:
            input_text, source_url, form_type, filing_date = result_filing
            date_label = f" (filed {filing_date})" if filing_date else ""
            errors.append(f"Auto-fetched {form_type}{date_label}: {source_url}")

    # Private company with no pasted text and no PDF — nothing to extract from.
    if not input_text and not pdf_bytes:
        errors.append(
            "NO_SOURCE_TEXT: Company name only mode auto-fetches SEC filings, "
            "which are only available for public companies. "
            "Paste an earnings transcript, investor memo, or press release to "
            "extract and stress-test claims for this company."
        )
        return [], 0.0, errors

    try:
        claims, extraction_cost = extract_claims(
            text=input_text,
            analysis_id=analysis_id,
            entity_id=company.entity_id,
            company_name=company.name,
            pdf_bytes=pdf_bytes,
        )
    except Exception as e:
        errors.append(f"ClaimExtractor: {e}")
        return [], 0.0, errors

    return claims, extraction_cost, errors
