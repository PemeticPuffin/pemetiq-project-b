"""
Verdict engine — Step 4 of the pipeline.

One Claude call per claim. Returns:
  - ClaimVerdictModel: overall verdict, evidence strength, reasoning
  - list[Evidence]: per-signal assessments
  - cost_usd: for spend tracking

Design: a single structured tool call returns both the per-signal breakdown
and the synthesis verdict. This keeps the reasoning grounded in the signals
rather than letting Claude synthesize abstractly.
"""
from __future__ import annotations

import json
from pathlib import Path

import anthropic

from config import settings
from schema.enums import (
    ClaimVerdict,
    EvidenceStrength,
    EvidenceVerdict,
)
from schema.models import Claim, ClaimVerdictModel, Evidence, Signal

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "verdict.txt"

_INPUT_COST_PER_M = 3.00
_OUTPUT_COST_PER_M = 15.00

_VERDICT_TOOL = {
    "name": "render_verdict",
    "description": "Assess each signal against the claim and synthesize an overall verdict.",
    "input_schema": {
        "type": "object",
        "properties": {
            "signal_assessments": {
                "type": "array",
                "description": "Per-signal assessments, one entry per signal provided.",
                "items": {
                    "type": "object",
                    "properties": {
                        "signal_id": {"type": "string"},
                        "verdict": {
                            "type": "string",
                            "enum": ["supporting", "contradicting", "insufficient"],
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "One sentence explaining why this signal supports, contradicts, or is insufficient.",
                        },
                    },
                    "required": ["signal_id", "verdict", "reasoning"],
                },
            },
            "overall_verdict": {
                "type": "string",
                "enum": [
                    "supported",
                    "partially_supported",
                    "contested",
                    "insufficient_evidence",
                    "not_testable",
                ],
            },
            "evidence_strength": {
                "type": "string",
                "enum": ["strong", "moderate", "weak"],
            },
            "reasoning": {
                "type": "string",
                "description": "2–4 sentence synthesis. State what evidence shows, name the key signal, identify the gap.",
            },
        },
        "required": ["signal_assessments", "overall_verdict", "evidence_strength", "reasoning"],
    },
}


def evaluate_claim(
    claim: Claim,
    signals: list[Signal],
) -> tuple[ClaimVerdictModel, list[Evidence], float]:
    """
    Evaluate a single claim against its matched signals.

    Args:
        claim: The Claim object to evaluate
        signals: Signals matched by the evidence mapper (may be empty)

    Returns:
        (ClaimVerdictModel, list[Evidence], cost_usd)
    """
    # Short-circuit: no signals → no point calling Claude
    if not signals and claim.testability == "no":
        verdict_model = ClaimVerdictModel(
            claim_id=claim.claim_id,
            verdict=ClaimVerdict.not_testable,
            evidence_strength=EvidenceStrength.weak,
            reasoning="This claim type cannot be evaluated using publicly observable signals.",
        )
        return verdict_model, [], 0.0

    if not signals:
        verdict_model = ClaimVerdictModel(
            claim_id=claim.claim_id,
            verdict=ClaimVerdict.insufficient_evidence,
            evidence_strength=EvidenceStrength.weak,
            reasoning="No relevant public signals were available to evaluate this claim.",
        )
        return verdict_model, [], 0.0

    system_prompt = _PROMPT_PATH.read_text()
    user_message = _format_user_message(claim, signals)

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1024,
        system=system_prompt,
        tools=[_VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "render_verdict"},
        messages=[{"role": "user", "content": user_message}],
    )

    cost_usd = _estimate_cost(response.usage)
    verdict_model, evidences = _parse_response(response, claim, signals)
    return verdict_model, evidences, cost_usd


def _format_user_message(claim: Claim, signals: list[Signal]) -> str:
    lines = [
        "## Claim",
        f"**Assertion:** {claim.assertion}",
        f"**Type:** {claim.claim_type.value}",
        f"**Specificity:** {claim.specificity.value}",
        f"**Testability:** {claim.testability.value}",
        f"**Temporal framing:** {claim.temporal_framing.value}",
        f"**Attribution clarity:** {claim.attribution_clarity.value}",
    ]
    if claim.is_implicit:
        lines.append(f"**Note:** This is an implicit claim (pattern #{claim.implicit_pattern_id})")

    lines.append("\n## Evidence Signals")
    for sig in signals:
        value_str = _format_value(sig.value)
        period_str = ""
        if sig.period_start and sig.period_end:
            period_str = f" ({sig.period_start} → {sig.period_end})"
        elif sig.period_end:
            period_str = f" (as of {sig.period_end})"
        lines.append(
            f"- **[{sig.signal_id}]** `{sig.signal_name}`: {value_str}{period_str} "
            f"| source: {sig.source.value} | tier: {sig.reliability_tier}"
        )

    return "\n".join(lines)


def _format_value(value) -> str:
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _parse_response(
    response: anthropic.types.Message,
    claim: Claim,
    signals: list[Signal],
) -> tuple[ClaimVerdictModel, list[Evidence]]:
    # Build a signal_id → Signal index for Evidence construction
    signal_index = {s.signal_id: s for s in signals}

    for block in response.content:
        if block.type != "tool_use" or block.name != "render_verdict":
            continue

        inp = block.input
        if isinstance(inp, str):
            try:
                inp = json.loads(inp)
            except (json.JSONDecodeError, TypeError):
                continue
        try:
            verdict_model = ClaimVerdictModel(
                claim_id=claim.claim_id,
                verdict=ClaimVerdict(inp["overall_verdict"]),
                evidence_strength=EvidenceStrength(inp["evidence_strength"]),
                reasoning=inp["reasoning"],
            )
        except (KeyError, ValueError):
            # Fallback if Claude returns unexpected values
            verdict_model = ClaimVerdictModel(
                claim_id=claim.claim_id,
                verdict=ClaimVerdict.insufficient_evidence,
                evidence_strength=EvidenceStrength.weak,
                reasoning="Verdict could not be parsed from model response.",
            )

        evidences: list[Evidence] = []
        for sa in inp.get("signal_assessments", []):
            if isinstance(sa, str):
                try:
                    sa = json.loads(sa)
                except (json.JSONDecodeError, TypeError):
                    continue
            sig_id = sa.get("signal_id", "")
            if sig_id not in signal_index:
                continue
            try:
                ev = Evidence(
                    claim_id=claim.claim_id,
                    signal_id=sig_id,
                    verdict=EvidenceVerdict(sa["verdict"]),
                    reasoning=sa.get("reasoning", ""),
                )
                evidences.append(ev)
            except (KeyError, ValueError):
                continue

        return verdict_model, evidences

    # No tool_use block found
    return ClaimVerdictModel(
        claim_id=claim.claim_id,
        verdict=ClaimVerdict.insufficient_evidence,
        evidence_strength=EvidenceStrength.weak,
        reasoning="No structured response returned by model.",
    ), []


def _estimate_cost(usage: anthropic.types.Usage) -> float:
    input_cost = (usage.input_tokens / 1_000_000) * _INPUT_COST_PER_M
    output_cost = (usage.output_tokens / 1_000_000) * _OUTPUT_COST_PER_M
    return round(input_cost + output_cost, 6)
