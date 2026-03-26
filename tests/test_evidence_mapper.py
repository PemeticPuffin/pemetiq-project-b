"""
Tests for pipeline/evidence_mapper.py

Pure logic — no network calls, no mocks needed.
"""
from __future__ import annotations

import pytest

from pipeline.evidence_mapper import CLAIM_SIGNAL_MAP, coverage_summary, map_evidence
from schema.enums import (
    AttributionClarity,
    ClaimType,
    DataSource,
    SignalType,
    Specificity,
    TemporalFraming,
    Testability,
)
from schema.models import Claim, Signal


# ── CLAIM_SIGNAL_MAP completeness ────────────────────────────────────────────

def test_all_claim_types_mapped():
    """Every ClaimType must have at least one SignalType in the map."""
    for ct in ClaimType:
        assert ct in CLAIM_SIGNAL_MAP, f"ClaimType.{ct.value} missing from CLAIM_SIGNAL_MAP"
        assert len(CLAIM_SIGNAL_MAP[ct]) > 0, f"ClaimType.{ct.value} has empty signal list"


def test_all_mapped_signal_types_are_valid():
    """Every SignalType referenced in the map must be a valid SignalType enum member."""
    valid = set(SignalType)
    for ct, signal_types in CLAIM_SIGNAL_MAP.items():
        for st in signal_types:
            assert st in valid, f"Unknown SignalType {st!r} in map for {ct.value}"


# ── map_evidence: basic matching ─────────────────────────────────────────────

def test_map_evidence_no_signals(growth_claim):
    """Claims with no signals return an empty list (not missing key)."""
    result = map_evidence([growth_claim], [])
    assert growth_claim.claim_id in result
    assert result[growth_claim.claim_id] == []


def test_map_evidence_matching_signal(growth_claim, revenue_signal):
    """A signal whose type is in the claim's map should be matched."""
    assert SignalType.revenue_growth in CLAIM_SIGNAL_MAP[ClaimType.growth]
    result = map_evidence([growth_claim], [revenue_signal])
    assert revenue_signal in result[growth_claim.claim_id]


def test_map_evidence_non_matching_signal(growth_claim, tech_stack_signal):
    """A signal whose type is NOT in the claim's map should not be matched."""
    assert SignalType.tech_stack not in CLAIM_SIGNAL_MAP[ClaimType.growth]
    result = map_evidence([growth_claim], [tech_stack_signal])
    assert tech_stack_signal not in result[growth_claim.claim_id]


def test_map_evidence_multiple_claims(growth_claim, product_claim, revenue_signal, tech_stack_signal):
    """Multiple claims are matched independently."""
    result = map_evidence(
        [growth_claim, product_claim],
        [revenue_signal, tech_stack_signal],
    )
    assert revenue_signal in result[growth_claim.claim_id]
    assert tech_stack_signal not in result[growth_claim.claim_id]
    assert tech_stack_signal in result[product_claim.claim_id]
    assert revenue_signal not in result[product_claim.claim_id]


def test_map_evidence_all_claims_present(growth_claim, product_claim):
    """All input claims appear as keys in the result, even with no signals."""
    result = map_evidence([growth_claim, product_claim], [])
    assert growth_claim.claim_id in result
    assert product_claim.claim_id in result


def test_map_evidence_same_signal_matched_to_multiple_claims(
    salesforce, growth_claim, product_claim
):
    """A signal type that appears in multiple ClaimType maps is matched to all relevant claims."""
    # oss_activity is in both team and product maps; github_commit_velocity too
    oss_signal = Signal(
        entity_id=salesforce.entity_id,
        signal_type=SignalType.oss_activity,
        signal_name="github_public_repos",
        value=42,
        source=DataSource.github_api,
        reliability_tier=2,
    )
    result = map_evidence([growth_claim, product_claim], [oss_signal])
    # growth doesn't include oss_activity
    assert oss_signal not in result[growth_claim.claim_id]
    # product does
    assert oss_signal in result[product_claim.claim_id]


# ── coverage_summary ─────────────────────────────────────────────────────────

def test_coverage_summary_empty_mapping():
    result = coverage_summary({})
    assert result["total_claims"] == 0
    assert result["coverage_pct"] == 0


def test_coverage_summary_all_empty():
    mapping = {"claim-1": [], "claim-2": []}
    result = coverage_summary(mapping)
    assert result["no_coverage"] == 2
    assert result["strong_coverage"] == 0
    assert result["partial_coverage"] == 0
    assert result["coverage_pct"] == 0.0


def _make_signals(n: int, salesforce) -> list[Signal]:
    return [
        Signal(
            entity_id=salesforce.entity_id,
            signal_type=SignalType.news_volume,
            signal_name=f"sig_{i}",
            value=i,
            source=DataSource.gdelt,
            reliability_tier=3,
        )
        for i in range(n)
    ]


def test_coverage_summary_strong(salesforce):
    signals = _make_signals(3, salesforce)
    mapping = {"claim-1": signals}
    result = coverage_summary(mapping)
    assert result["strong_coverage"] == 1
    assert result["partial_coverage"] == 0
    assert result["no_coverage"] == 0
    assert result["coverage_pct"] == 100.0


def test_coverage_summary_partial(salesforce):
    signals = _make_signals(2, salesforce)
    mapping = {"claim-1": signals}
    result = coverage_summary(mapping)
    assert result["partial_coverage"] == 1
    assert result["strong_coverage"] == 0


def test_coverage_summary_mixed(salesforce):
    mapping = {
        "claim-strong": _make_signals(4, salesforce),
        "claim-partial": _make_signals(1, salesforce),
        "claim-empty": [],
    }
    result = coverage_summary(mapping)
    assert result["total_claims"] == 3
    assert result["strong_coverage"] == 1
    assert result["partial_coverage"] == 1
    assert result["no_coverage"] == 1
    assert result["coverage_pct"] == pytest.approx(66.7, abs=0.1)
