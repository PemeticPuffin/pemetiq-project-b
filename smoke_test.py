"""
End-to-end smoke test — runs the full pipeline against a short Salesforce snippet.
Cost: ~$0.02–0.05 (1 extraction call + ~5 verdict calls on a short text).

Usage:
    python smoke_test.py
"""
import os
import sys

# Minimal text — enough to generate ~5 claims without running up cost
SAMPLE_TEXT = """
Salesforce delivered record revenue of $9.9 billion in fiscal Q4 2025, representing
20% year-over-year growth. We are the world's #1 CRM platform and have been for
over a decade. Our AI platform, Agentforce, is already deployed by more than 1,000
enterprise customers. We added 3,200 net new employees this fiscal year, bringing
total headcount to 72,000. Operating cash flow exceeded $6 billion, and we expect
fiscal 2026 revenue of $37.9 billion.
"""

COMPANY_NAME = "Salesforce"
COMPANY_DOMAIN = "salesforce.com"


def main():
    print("=" * 60)
    print("Pemetiq Narrative Stress Test — Smoke Test")
    print("=" * 60)

    # ── 1. CIK lookup ────────────────────────────────────────────
    print("\n[1/5] CIK lookup...")
    from utils.company_lookup import lookup_cik
    cik, ticker = lookup_cik(COMPANY_NAME)
    print(f"      CIK: {cik}  Ticker: {ticker}")
    assert cik, "CIK lookup failed — check network / EDGAR availability"

    # ── 2. EDGAR fetcher ─────────────────────────────────────────
    print("\n[2/5] EDGAR fetcher (XBRL financials)...")
    from fetchers.edgar import EdgarFetcher
    from schema.enums import CompanyType
    from schema.models import Company

    company = Company(
        entity_id="salesforce",
        name=COMPANY_NAME,
        ticker=ticker,
        cik=cik,
        domain=COMPANY_DOMAIN,
        company_type=CompanyType.public,
    )

    edgar = EdgarFetcher()
    signals = edgar.fetch(company)
    print(f"      Signals returned: {len(signals)}")
    for s in signals:
        print(f"        {s.signal_name}: {s.value} ({s.source.value}, tier {s.reliability_tier})")
    assert signals, "EDGAR returned no signals — check CIK or EDGAR availability"

    # ── 3. Google Trends fetcher ──────────────────────────────────
    print("\n[3/5] Google Trends fetcher...")
    from fetchers.google_trends import GoogleTrendsFetcher
    gt = GoogleTrendsFetcher()
    gt_signals = gt.fetch(company, competitors=["HubSpot", "ServiceNow"])
    print(f"      Signals returned: {len(gt_signals)}")
    for s in gt_signals:
        print(f"        {s.signal_name}: {s.value}")

    # ── 4. Claim extraction ───────────────────────────────────────
    print("\n[4/5] Claim extraction (Claude API call)...")
    from pipeline.claim_extractor import extract_claims
    claims, extraction_cost = extract_claims(
        text=SAMPLE_TEXT,
        analysis_id="smoke-test-001",
        entity_id="salesforce",
        company_name=COMPANY_NAME,
    )
    print(f"      Claims extracted: {len(claims)}  Cost: ${extraction_cost:.4f}")
    for c in claims:
        tag = "[implicit]" if c.is_implicit else ""
        print(f"        [{c.claim_type.value}] {c.assertion[:80]} {tag}")
    assert claims, "No claims extracted — check prompt or API key"

    # ── 5. Evidence mapping + verdict (first 3 claims only) ───────
    print("\n[5/5] Evidence mapping + verdict engine (first 3 claims)...")
    from pipeline.evidence_mapper import map_evidence, coverage_summary
    from pipeline.verdict_engine import evaluate_claim

    all_signals = signals + gt_signals
    evidence_map = map_evidence(claims, all_signals)
    coverage = coverage_summary(evidence_map)
    print(f"      Coverage: {coverage}")

    total_verdict_cost = 0.0
    for claim in claims[:3]:
        matched = evidence_map.get(claim.claim_id, [])
        verdict, evs, cost = evaluate_claim(claim, matched)
        total_verdict_cost += cost
        print(f"\n        Claim:    {claim.assertion[:70]}")
        print(f"        Verdict:  {verdict.verdict.value}  [{verdict.evidence_strength.value}]")
        print(f"        Reason:   {verdict.reasoning[:120]}")

    total_cost = extraction_cost + total_verdict_cost
    print(f"\n      Verdict cost (3 claims): ${total_verdict_cost:.4f}")
    print(f"      Total cost this run:    ${total_cost:.4f}")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SMOKE TEST PASSED")
    print(f"  Claims: {len(claims)}  |  Signals: {len(all_signals)}  |  Cost: ${total_cost:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
