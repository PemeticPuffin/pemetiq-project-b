"""
Tests for pipeline/verdict_engine.py

Uses unittest.mock to avoid live Claude API calls.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pipeline.verdict_engine import (
    _estimate_cost,
    _format_user_message,
    _parse_response,
    evaluate_claim,
)
from schema.enums import (
    ClaimVerdict,
    EvidenceStrength,
    EvidenceVerdict,
    Testability,
)
from schema.models import ClaimVerdictModel, Evidence


# ── _estimate_cost ────────────────────────────────────────────────────────────

def test_estimate_cost_zero():
    usage = SimpleNamespace(input_tokens=0, output_tokens=0)
    assert _estimate_cost(usage) == 0.0


def test_estimate_cost_typical():
    usage = SimpleNamespace(input_tokens=1000, output_tokens=300)
    expected = (1000 / 1_000_000) * 3.00 + (300 / 1_000_000) * 15.00
    assert _estimate_cost(usage) == pytest.approx(expected, rel=1e-4)


# ── _format_user_message ──────────────────────────────────────────────────────

def test_format_user_message_contains_assertion(growth_claim, revenue_signal):
    msg = _format_user_message(growth_claim, [revenue_signal])
    assert growth_claim.assertion in msg


def test_format_user_message_contains_signal_name(growth_claim, revenue_signal):
    msg = _format_user_message(growth_claim, [revenue_signal])
    assert revenue_signal.signal_name in msg


def test_format_user_message_implicit_note(not_testable_claim):
    # Make it implicit to test the implicit path
    not_testable_claim.is_implicit = True
    not_testable_claim.implicit_pattern_id = 5
    msg = _format_user_message(not_testable_claim, [])
    assert "implicit" in msg.lower()
    assert "#5" in msg


def test_format_user_message_no_signals(growth_claim):
    msg = _format_user_message(growth_claim, [])
    assert "Evidence Signals" in msg


def test_format_user_message_formats_float_signal(growth_claim, salesforce):
    from schema.enums import DataSource, SignalType
    from schema.models import Signal
    sig = Signal(
        entity_id=salesforce.entity_id,
        signal_type=SignalType.gross_margin,
        signal_name="gross_margin_pct",
        value=73.456789,
        unit="pct",
        source=DataSource.edgar_xbrl,
        reliability_tier=1,
    )
    msg = _format_user_message(growth_claim, [sig])
    assert "73.46" in msg  # formatted as {:,.2f}


# ── short-circuit paths in evaluate_claim ────────────────────────────────────

def test_evaluate_claim_no_signals_not_testable(not_testable_claim):
    """Testability=no + no signals → not_testable verdict, zero cost."""
    verdict, evidences, cost = evaluate_claim(not_testable_claim, [])
    assert verdict.verdict == ClaimVerdict.not_testable
    assert cost == 0.0
    assert evidences == []


def test_evaluate_claim_no_signals_testable(growth_claim):
    """Testable claim with no signals → insufficient_evidence, zero cost."""
    verdict, evidences, cost = evaluate_claim(growth_claim, [])
    assert verdict.verdict == ClaimVerdict.insufficient_evidence
    assert cost == 0.0


# ── _parse_response ───────────────────────────────────────────────────────────

def _make_verdict_response(
    overall_verdict: str,
    evidence_strength: str,
    reasoning: str,
    signal_assessments: list[dict],
    input_tokens: int = 500,
    output_tokens: int = 200,
):
    block = SimpleNamespace(
        type="tool_use",
        name="render_verdict",
        input={
            "overall_verdict": overall_verdict,
            "evidence_strength": evidence_strength,
            "reasoning": reasoning,
            "signal_assessments": signal_assessments,
        },
    )
    return SimpleNamespace(
        content=[block],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_parse_response_supported_verdict(growth_claim, revenue_signal):
    response = _make_verdict_response(
        overall_verdict="supported",
        evidence_strength="strong",
        reasoning="EDGAR confirms 20.5% YoY revenue growth.",
        signal_assessments=[{
            "signal_id": revenue_signal.signal_id,
            "verdict": "supporting",
            "reasoning": "Revenue growth data directly confirms the claim.",
        }],
    )
    verdict_model, evidences = _parse_response(response, growth_claim, [revenue_signal])
    assert verdict_model.verdict == ClaimVerdict.supported
    assert verdict_model.evidence_strength == EvidenceStrength.strong
    assert len(evidences) == 1
    assert evidences[0].verdict == EvidenceVerdict.supporting


def test_parse_response_contested_verdict(growth_claim, revenue_signal):
    response = _make_verdict_response(
        overall_verdict="contested",
        evidence_strength="moderate",
        reasoning="Data shows only 12% growth, not the claimed 20%.",
        signal_assessments=[{
            "signal_id": revenue_signal.signal_id,
            "verdict": "contradicting",
            "reasoning": "EDGAR shows 12% growth, contradicting the 20% claim.",
        }],
    )
    verdict_model, evidences = _parse_response(response, growth_claim, [revenue_signal])
    assert verdict_model.verdict == ClaimVerdict.contested
    assert evidences[0].verdict == EvidenceVerdict.contradicting


def test_parse_response_unknown_signal_id_skipped(growth_claim, revenue_signal):
    """signal_id not in the signal list should be silently skipped."""
    response = _make_verdict_response(
        overall_verdict="insufficient_evidence",
        evidence_strength="weak",
        reasoning="No relevant signals.",
        signal_assessments=[{
            "signal_id": "unknown-id-not-in-list",
            "verdict": "supporting",
            "reasoning": "Some reasoning.",
        }],
    )
    _, evidences = _parse_response(response, growth_claim, [revenue_signal])
    assert len(evidences) == 0


def test_parse_response_fallback_on_invalid_verdict(growth_claim, revenue_signal):
    """Invalid overall_verdict enum value → fallback to insufficient_evidence."""
    block = SimpleNamespace(
        type="tool_use",
        name="render_verdict",
        input={
            "overall_verdict": "not_a_real_verdict",
            "evidence_strength": "strong",
            "reasoning": "Some reasoning.",
            "signal_assessments": [],
        },
    )
    response = SimpleNamespace(content=[block])
    verdict_model, _ = _parse_response(response, growth_claim, [revenue_signal])
    assert verdict_model.verdict == ClaimVerdict.insufficient_evidence


def test_parse_response_no_tool_use_block(growth_claim, revenue_signal):
    """No tool_use block → fallback verdict."""
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    verdict_model, evidences = _parse_response(response, growth_claim, [revenue_signal])
    assert verdict_model.verdict == ClaimVerdict.insufficient_evidence
    assert evidences == []


# ── evaluate_claim: integration with mock ────────────────────────────────────

@patch("pipeline.verdict_engine.anthropic.Anthropic")
def test_evaluate_claim_calls_api_with_signals(mock_cls, growth_claim, revenue_signal):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_verdict_response(
        overall_verdict="supported",
        evidence_strength="strong",
        reasoning="Confirmed by EDGAR.",
        signal_assessments=[{
            "signal_id": revenue_signal.signal_id,
            "verdict": "supporting",
            "reasoning": "Matches data.",
        }],
    )

    verdict, evidences, cost = evaluate_claim(growth_claim, [revenue_signal])

    assert mock_client.messages.create.called
    assert verdict.verdict == ClaimVerdict.supported
    assert cost > 0.0
    assert len(evidences) == 1
