"""
Evidence mapper — Step 3 of the pipeline.

Two responsibilities:
  1. Static map: ClaimType → relevant SignalTypes (encodes domain judgment)
  2. Match function: given claims + fetched signals, returns claim_id → list[Signal]

This is the non-AI layer of value — the mapping itself reflects 15+ years of
domain judgment about which signals actually speak to which claim types.
The verdict engine (Step 4) consumes this output.
"""
from __future__ import annotations

from schema.enums import ClaimType, SignalType
from schema.models import Claim, Signal

# ---------------------------------------------------------------------------
# Layer 1: ClaimType → [SignalType]
# Static. Changes here represent framework decisions, not engineering changes.
# ---------------------------------------------------------------------------

CLAIM_SIGNAL_MAP: dict[ClaimType, list[SignalType]] = {

    ClaimType.growth: [
        SignalType.annual_revenue,        # absolute revenue (EDGAR) — anchors the base
        SignalType.revenue_growth,        # YoY growth rate (EDGAR)
        SignalType.search_momentum,       # brand/traffic trend proxy (Google Trends)
        SignalType.hiring_volume,         # headcount growth as leading indicator (Adzuna)
        SignalType.github_commit_velocity, # product output velocity (GitHub)
        SignalType.news_volume,           # press velocity as growth signal (GDELT)
    ],

    ClaimType.market_position: [
        SignalType.search_share_vs_competitors,  # relative search interest (Google Trends)
        SignalType.app_store_rating,             # consumer product standing (App Store)
        SignalType.news_volume,                  # press volume vs. narrative (GDELT)
        SignalType.oss_activity,                 # technical presence / credibility (GitHub)
        SignalType.tech_stack,                   # tech sophistication signals (Wappalyzer)
        SignalType.annual_revenue,               # revenue scale for "leader" claims (EDGAR)
    ],

    ClaimType.team: [
        SignalType.hiring_volume,         # open roles = hiring momentum (Adzuna)
        SignalType.hiring_mix,            # function breakdown (Adzuna) — tests "AI team" claims
        SignalType.github_commit_velocity, # engineering output (GitHub)
        SignalType.oss_activity,          # public technical contribution (GitHub)
    ],

    ClaimType.product: [
        SignalType.tech_stack,            # actual stack vs. claimed capabilities (Wappalyzer)
        SignalType.oss_activity,          # open source presence supports "proprietary tech" scrutiny
        SignalType.github_commit_velocity, # active development vs. maintenance mode
        SignalType.pricing_page_history,  # pricing page removals / changes (Wayback)
        SignalType.app_store_rating,      # mobile product quality signal
        SignalType.mobile_ratings,        # breadth of mobile presence
        SignalType.hiring_mix,            # AI/ML hiring supports or contradicts AI product claims
    ],

    ClaimType.unit_economics: [
        SignalType.annual_revenue,        # revenue scale (EDGAR)
        SignalType.revenue_growth,        # growth rate (EDGAR)
        SignalType.gross_margin,          # margin profile (EDGAR)
        SignalType.operating_income,      # profitability (EDGAR)
        SignalType.eps,                   # earnings (EDGAR)
        SignalType.filing_language_change, # metric definition changes = red flag (EDGAR 8-K)
        SignalType.pricing_page_history,  # pricing changes as unit economics signal (Wayback)
    ],
}

# Signal types that are broadly relevant regardless of claim type
# (not added to every claim — used to supplement when primary signals are sparse)
_SUPPLEMENTAL: list[SignalType] = [
    SignalType.news_volume,
]


# ---------------------------------------------------------------------------
# Layer 2: Match function
# ---------------------------------------------------------------------------

def map_evidence(
    claims: list[Claim],
    signals: list[Signal],
) -> dict[str, list[Signal]]:
    """
    Match fetched signals to claims based on the static ClaimType → SignalType map.

    Args:
        claims: Extracted Claim objects from the claim extractor
        signals: All Signal objects fetched by the data layer

    Returns:
        claim_id → list[Signal] — only signals relevant to that claim type.
        Claims with no matching signals are included with an empty list
        (the verdict engine will mark them as insufficient_evidence or not_testable).
    """
    # Index signals by type for O(1) lookup
    signals_by_type: dict[SignalType, list[Signal]] = {}
    for signal in signals:
        signals_by_type.setdefault(signal.signal_type, []).append(signal)

    result: dict[str, list[Signal]] = {}

    for claim in claims:
        relevant_types = CLAIM_SIGNAL_MAP.get(claim.claim_type, [])
        matched: list[Signal] = []
        for stype in relevant_types:
            matched.extend(signals_by_type.get(stype, []))

        result[claim.claim_id] = matched

    return result


def coverage_summary(mapping: dict[str, list[Signal]]) -> dict:
    """
    Returns a summary of signal coverage for UI/debugging.
    Shows how many claims have strong, partial, or no evidence.
    """
    strong = sum(1 for sigs in mapping.values() if len(sigs) >= 3)
    partial = sum(1 for sigs in mapping.values() if 1 <= len(sigs) < 3)
    empty = sum(1 for sigs in mapping.values() if len(sigs) == 0)
    total = len(mapping)

    return {
        "total_claims": total,
        "strong_coverage": strong,   # 3+ signals
        "partial_coverage": partial, # 1–2 signals
        "no_coverage": empty,        # 0 signals → insufficient_evidence
        "coverage_pct": round((strong + partial) / total * 100, 1) if total else 0,
    }
