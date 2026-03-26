"""
Live end-to-end smoke test — makes real API calls.

Cost: ~$0.02–0.05 per run (1 extraction + ~3 verdict calls).

Run explicitly with:
    pytest -m smoke -s

The -s flag shows print output (signal values, verdicts, cost).
NOT included in the default test run (pytest tests/).
"""
import pytest

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


@pytest.mark.smoke
def test_cik_lookup():
    """EDGAR CIK lookup resolves Salesforce to a valid CIK."""
    from utils.company_lookup import lookup_cik
    cik, ticker = lookup_cik(COMPANY_NAME)
    print(f"\n  CIK: {cik}  Ticker: {ticker}")
    assert cik, "CIK lookup returned None — check network / EDGAR availability"
    assert cik.isdigit(), f"CIK should be numeric, got: {cik!r}"


@pytest.mark.smoke
def test_edgar_fetcher_live():
    """EDGAR XBRL fetcher returns financial signals for Salesforce."""
    from utils.company_lookup import lookup_cik
    from fetchers.edgar import EdgarFetcher
    from schema.enums import CompanyType, SignalType
    from schema.models import Company

    cik, ticker = lookup_cik(COMPANY_NAME)
    company = Company(
        entity_id="salesforce",
        name=COMPANY_NAME,
        ticker=ticker,
        cik=cik,
        domain=COMPANY_DOMAIN,
        company_type=CompanyType.public,
    )

    signals = EdgarFetcher().fetch(company)
    print(f"\n  Signals returned: {len(signals)}")
    for s in signals:
        print(f"    {s.signal_name}: {s.value} ({s.source.value}, tier {s.reliability_tier})")

    assert signals, "EDGAR returned no signals — check CIK or EDGAR availability"
    signal_types = {s.signal_type for s in signals}
    assert SignalType.annual_revenue in signal_types, "Expected annual_revenue signal"


@pytest.mark.smoke
def test_claim_extraction_live():
    """Claude API extracts structured claims from the sample Salesforce text."""
    from pipeline.claim_extractor import extract_claims

    claims, cost = extract_claims(
        text=SAMPLE_TEXT,
        analysis_id="smoke-pytest-001",
        entity_id="salesforce",
        company_name=COMPANY_NAME,
    )
    print(f"\n  Claims extracted: {len(claims)}  Cost: ${cost:.4f}")
    for c in claims:
        tag = " [implicit]" if c.is_implicit else ""
        print(f"    [{c.claim_type.value}] {c.assertion[:80]}{tag}")

    assert claims, "No claims extracted — check ANTHROPIC_API_KEY or prompt"
    assert len(claims) >= 3, f"Expected at least 3 claims, got {len(claims)}"
    assert cost > 0.0, "Cost should be non-zero for a real API call"


@pytest.mark.smoke
def test_verdict_engine_live():
    """Full pipeline: claim extraction → evidence mapping → verdict for first 3 claims."""
    from utils.company_lookup import lookup_cik
    from fetchers.edgar import EdgarFetcher
    from fetchers.google_trends import GoogleTrendsFetcher
    from pipeline.claim_extractor import extract_claims
    from pipeline.evidence_mapper import map_evidence, coverage_summary
    from pipeline.verdict_engine import evaluate_claim
    from schema.enums import CompanyType
    from schema.models import Company

    cik, ticker = lookup_cik(COMPANY_NAME)
    company = Company(
        entity_id="salesforce",
        name=COMPANY_NAME,
        ticker=ticker,
        cik=cik,
        domain=COMPANY_DOMAIN,
        company_type=CompanyType.public,
    )

    # Gather signals (two free sources)
    edgar_signals = EdgarFetcher().fetch(company)
    gt_signals = GoogleTrendsFetcher().fetch(company, competitors=["HubSpot", "ServiceNow"])
    all_signals = edgar_signals + gt_signals
    print(f"\n  Signals gathered: {len(all_signals)}")

    # Extract claims
    claims, extraction_cost = extract_claims(
        text=SAMPLE_TEXT,
        analysis_id="smoke-pytest-002",
        entity_id="salesforce",
        company_name=COMPANY_NAME,
    )
    print(f"  Claims extracted: {len(claims)}  (extraction cost: ${extraction_cost:.4f})")

    # Map evidence
    evidence_map = map_evidence(claims, all_signals)
    coverage = coverage_summary(evidence_map)
    print(f"  Coverage: {coverage}")

    # Run verdicts on first 3 claims
    verdict_cost = 0.0
    for claim in claims[:3]:
        matched = evidence_map.get(claim.claim_id, [])
        verdict, _, cost = evaluate_claim(claim, matched)
        verdict_cost += cost
        print(f"\n  Claim:   {claim.assertion[:70]}")
        print(f"  Verdict: {verdict.verdict.value}  [{verdict.evidence_strength.value}]")
        print(f"  Reason:  {verdict.reasoning[:120]}")

    total_cost = extraction_cost + verdict_cost
    print(f"\n  Total cost this run: ${total_cost:.4f}")

    assert claims, "No claims extracted"
    assert coverage["total_claims"] > 0
    assert total_cost < 0.50, f"Cost ${total_cost:.4f} exceeded $0.50 safety threshold"
