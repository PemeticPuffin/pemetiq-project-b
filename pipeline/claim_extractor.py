"""
Claim extraction pipeline step.
Sends raw text (or a native PDF document) to Claude with a structured tool call.
Returns list[Claim] and the API cost in USD.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import anthropic

from config import settings
from schema.enums import (
    AttributionClarity,
    ClaimType,
    Specificity,
    TemporalFraming,
    Testability,
)
from schema.models import Claim

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "claim_extraction.txt"

# Sonnet 3.5/4.x pricing (per million tokens)
_INPUT_COST_PER_M = 3.00
_OUTPUT_COST_PER_M = 15.00

def _is_testable_claim(claim: Claim) -> bool:
    """
    Return False for claims that will produce no analytical value for the audience.

    Kept:
    - All implicit claims (26-pattern flags are analytically valuable even if not directly testable)
    - All forward-looking claims (analysts want to know what management said they'd do)
    - All quantitative and comparative explicit claims
    - Qualitative claims with at least partial testability

    Dropped:
    - Explicit, non-forward, testability=no claims → always produce "Not Testable" verdict,
      waste a Claude call, and dilute results for the analyst audience
    - Unit economics past quantitative → EDGAR annual signals can't verify sub-period figures
    """
    # Always keep implicit claims — they are analytical red flags, not direct assertions
    if claim.is_implicit:
        return True

    # Always keep forward guidance — analysts specifically want to track what was promised
    if claim.temporal_framing == TemporalFraming.forward:
        return True

    # Drop explicit claims that are explicitly not testable from public signals
    # These produce "Not Testable" verdicts with no signal evidence — no value to the audience
    if claim.testability == Testability.no:
        return False

    # Unit economics past quantitative → sub-period figures EDGAR annual data cannot verify
    if (
        claim.claim_type == ClaimType.unit_economics
        and claim.temporal_framing == TemporalFraming.past
        and claim.specificity == Specificity.quantitative
    ):
        return False

    return True


_EXTRACT_TOOL = {
    "name": "extract_claims",
    "description": "Extract all narrative claims from the provided text, including implicit claims.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "assertion": {"type": "string"},
                        "claim_type": {
                            "type": "string",
                            "enum": ["growth", "market_position", "team", "product", "unit_economics"],
                        },
                        "specificity": {
                            "type": "string",
                            "enum": ["quantitative", "comparative", "qualitative"],
                        },
                        "testability": {
                            "type": "string",
                            "enum": ["yes", "partial", "no"],
                        },
                        "temporal_framing": {
                            "type": "string",
                            "enum": ["past", "present", "forward"],
                        },
                        "attribution_clarity": {
                            "type": "string",
                            "enum": ["clear", "ambiguous", "unverifiable"],
                        },
                        "is_implicit": {"type": "boolean"},
                        "implicit_pattern_id": {
                            "type": ["integer", "null"],
                            "description": "Pattern ID (1–40) if is_implicit is true, else null",
                        },
                    },
                    "required": [
                        "assertion",
                        "claim_type",
                        "specificity",
                        "testability",
                        "temporal_framing",
                        "attribution_clarity",
                        "is_implicit",
                        "implicit_pattern_id",
                    ],
                },
            }
        },
        "required": ["claims"],
    },
}


def extract_claims(
    text: str | None,
    analysis_id: str,
    entity_id: str,
    company_name: str,
    pdf_bytes: bytes | None = None,
) -> tuple[list[Claim], float]:
    """
    Extract claims from raw text or a native PDF document using Claude.

    When pdf_bytes is provided it is sent as a native document block so Claude
    reads the full PDF — including images, charts, and layout — rather than
    receiving pre-extracted text.  text is ignored when pdf_bytes is set.

    Args:
        text: Raw input text (pitch deck paste, earnings transcript, investor memo)
        analysis_id: FK for the parent Analysis object
        entity_id: Company entity_id
        company_name: Used in user message for context
        pdf_bytes: Raw PDF bytes; when provided, sent as a native document block

    Returns:
        (claims, cost_usd)
    """
    system_prompt = _PROMPT_PATH.read_text()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    if pdf_bytes:
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        user_content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_b64,
                },
                "title": f"{company_name} — uploaded document",
            },
            {
                "type": "text",
                "text": (
                    f"Company: {company_name}\n\n"
                    "Extract all claims from the document above."
                ),
            },
        ]
    else:
        user_content = (
            f"Company: {company_name}\n\n"
            f"---\n\n{text}\n\n---\n\n"
            "Extract all claims from the text above."
        )

    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=16384,
        system=system_prompt,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_claims"},
        messages=[{"role": "user", "content": user_content}],
    )

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Claim extraction response truncated (max_tokens hit). "
            f"Input text may be too long ({len(text)} chars). "
            f"Reduce text length or increase max_tokens."
        )

    cost_usd = _estimate_cost(response.usage)
    claims = _parse_response(response, analysis_id, entity_id)
    return claims[:20], cost_usd


def _parse_response(
    response: anthropic.types.Message,
    analysis_id: str,
    entity_id: str,
) -> list[Claim]:
    claims: list[Claim] = []

    for block in response.content:
        if block.type != "tool_use" or block.name != "extract_claims":
            continue

        raw_claims = block.input.get("claims", [])
        for rc in raw_claims:
            try:
                claim = Claim(
                    analysis_id=analysis_id,
                    entity_id=entity_id,
                    assertion=rc["assertion"],
                    claim_type=ClaimType(rc["claim_type"]),
                    specificity=Specificity(rc["specificity"]),
                    testability=Testability(rc["testability"]),
                    temporal_framing=TemporalFraming(rc["temporal_framing"]),
                    attribution_clarity=AttributionClarity(rc["attribution_clarity"]),
                    is_implicit=rc.get("is_implicit", False),
                    implicit_pattern_id=rc.get("implicit_pattern_id"),
                )
                if _is_testable_claim(claim):
                    claims.append(claim)
            except (KeyError, ValueError):
                # Skip malformed entries — don't crash the pipeline
                continue

    return claims


def _estimate_cost(usage: anthropic.types.Usage) -> float:
    input_cost = (usage.input_tokens / 1_000_000) * _INPUT_COST_PER_M
    output_cost = (usage.output_tokens / 1_000_000) * _OUTPUT_COST_PER_M
    return round(input_cost + output_cost, 6)
