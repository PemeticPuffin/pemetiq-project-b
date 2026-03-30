"""
Tests for pipeline/claim_extractor.py

Uses unittest.mock to avoid live Claude API calls.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pipeline.claim_extractor import _estimate_cost, _parse_response, extract_claims
from schema.enums import (
    AttributionClarity,
    ClaimType,
    Specificity,
    TemporalFraming,
    Testability,
)
from schema.models import Claim


# ── _estimate_cost ────────────────────────────────────────────────────────────

def test_estimate_cost_zero():
    usage = SimpleNamespace(input_tokens=0, output_tokens=0)
    assert _estimate_cost(usage) == 0.0


def test_estimate_cost_input_only():
    # 1M input tokens at $3/M = $3.00
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0)
    assert _estimate_cost(usage) == pytest.approx(3.00)


def test_estimate_cost_output_only():
    # 1M output tokens at $15/M = $15.00
    usage = SimpleNamespace(input_tokens=0, output_tokens=1_000_000)
    assert _estimate_cost(usage) == pytest.approx(15.00)


def test_estimate_cost_small_run():
    # Typical small run: ~2K input + ~500 output
    usage = SimpleNamespace(input_tokens=2000, output_tokens=500)
    expected = (2000 / 1_000_000) * 3.00 + (500 / 1_000_000) * 15.00
    assert _estimate_cost(usage) == pytest.approx(expected, rel=1e-4)


# ── _parse_response ───────────────────────────────────────────────────────────

def _make_tool_use_block(claims_data: list[dict]):
    block = SimpleNamespace(
        type="tool_use",
        name="extract_claims",
        input={"claims": claims_data},
    )
    response = SimpleNamespace(content=[block])
    return response


def test_parse_response_valid_claim():
    response = _make_tool_use_block([{
        "assertion": "Revenue grew 20% YoY",
        "claim_type": "growth",
        "specificity": "quantitative",
        "testability": "yes",
        "temporal_framing": "past",
        "attribution_clarity": "clear",
        "is_implicit": False,
        "implicit_pattern_id": None,
    }])
    claims = _parse_response(response, "analysis-1", "salesforce")
    assert len(claims) == 1
    assert claims[0].assertion == "Revenue grew 20% YoY"
    assert claims[0].claim_type == ClaimType.growth


def test_parse_response_skips_malformed_entries():
    """Missing required fields should be skipped silently, not crash."""
    response = _make_tool_use_block([
        {
            "assertion": "Valid claim",
            "claim_type": "growth",
            "specificity": "quantitative",
            "testability": "yes",
            "temporal_framing": "past",
            "attribution_clarity": "clear",
            "is_implicit": False,
            "implicit_pattern_id": None,
        },
        {
            "assertion": "Malformed — missing required fields",
            # claim_type missing
        },
    ])
    claims = _parse_response(response, "analysis-1", "salesforce")
    assert len(claims) == 1


def test_parse_response_skips_invalid_enum():
    """Invalid enum values should be skipped, not crash."""
    response = _make_tool_use_block([{
        "assertion": "Some claim",
        "claim_type": "not_a_real_type",  # invalid
        "specificity": "quantitative",
        "testability": "yes",
        "temporal_framing": "past",
        "attribution_clarity": "clear",
        "is_implicit": False,
        "implicit_pattern_id": None,
    }])
    claims = _parse_response(response, "analysis-1", "salesforce")
    assert len(claims) == 0


def test_parse_response_no_tool_use_block():
    """Response with no tool_use block returns empty list."""
    text_block = SimpleNamespace(type="text", text="Sorry, I can't do that.")
    response = SimpleNamespace(content=[text_block])
    claims = _parse_response(response, "analysis-1", "salesforce")
    assert claims == []


def test_parse_response_implicit_claim_filtered():
    """Implicit claims are filtered out — they reliably produce insufficient evidence."""
    response = _make_tool_use_block([{
        "assertion": "Implied: the market is growing rapidly",
        "claim_type": "market_position",
        "specificity": "qualitative",
        "testability": "partial",
        "temporal_framing": "present",
        "attribution_clarity": "ambiguous",
        "is_implicit": True,
        "implicit_pattern_id": 7,
    }])
    claims = _parse_response(response, "analysis-1", "salesforce")
    assert len(claims) == 0


def test_parse_response_caps_at_20_claims():
    """Hard cap of 20 claims regardless of how many the model returns."""
    raw_claims = [
        {
            "assertion": f"Claim {i}",
            "claim_type": "growth",
            "specificity": "qualitative",
            "testability": "partial",
            "temporal_framing": "present",
            "attribution_clarity": "clear",
            "is_implicit": False,
            "implicit_pattern_id": None,
        }
        for i in range(30)
    ]
    response = _make_tool_use_block(raw_claims)
    claims = _parse_response(response, "analysis-1", "salesforce")
    # _parse_response itself doesn't cap; extract_claims does via [:20]
    # Ensure the full list is parseable (cap tested at extract_claims level)
    assert len(claims) == 30  # _parse_response returns all; extract_claims slices


# ── extract_claims: integration with mock ────────────────────────────────────

def _mock_anthropic_response(claims_data: list[dict], input_tokens=500, output_tokens=200):
    block = SimpleNamespace(
        type="tool_use",
        name="extract_claims",
        input={"claims": claims_data},
    )
    return SimpleNamespace(
        content=[block],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@patch("pipeline.claim_extractor.anthropic.Anthropic")
def test_extract_claims_returns_claims_and_cost(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_anthropic_response([{
        "assertion": "Revenue grew 20% YoY",
        "claim_type": "growth",
        "specificity": "quantitative",
        "testability": "yes",
        "temporal_framing": "past",
        "attribution_clarity": "clear",
        "is_implicit": False,
        "implicit_pattern_id": None,
    }])

    claims, cost = extract_claims(
        text="Revenue grew 20% YoY",
        analysis_id="test-001",
        entity_id="salesforce",
        company_name="Salesforce",
    )
    assert len(claims) == 1
    assert cost > 0.0
    assert isinstance(claims[0], Claim)


@patch("pipeline.claim_extractor.anthropic.Anthropic")
def test_extract_claims_caps_at_20(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    raw = [
        {
            "assertion": f"Claim {i}",
            "claim_type": "growth",
            "specificity": "qualitative",
            "testability": "partial",
            "temporal_framing": "present",
            "attribution_clarity": "clear",
            "is_implicit": False,
            "implicit_pattern_id": None,
        }
        for i in range(25)
    ]
    mock_client.messages.create.return_value = _mock_anthropic_response(raw)

    claims, _ = extract_claims(
        text="some text", analysis_id="test-001",
        entity_id="co", company_name="Company",
    )
    assert len(claims) == 20


@patch("pipeline.claim_extractor.anthropic.Anthropic")
def test_extract_claims_raises_on_max_tokens(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = SimpleNamespace(
        content=[],
        stop_reason="max_tokens",
        usage=SimpleNamespace(input_tokens=8000, output_tokens=8192),
    )

    with pytest.raises(RuntimeError, match="truncated"):
        extract_claims(
            text="x" * 10000, analysis_id="test-001",
            entity_id="co", company_name="Company",
        )
