"""
Claim drift — how a company's own stated narrative shifted between two filings.

Compares the MD&A of the latest filing against its year-ago comparable and
surfaces claims that were walked back, dropped, escalated, reversed, or newly
added. This is the temporal companion to the core stress test: instead of
"is this claim true?", it asks "is management quietly walking back what it
used to say?".

Uses a Claude tool call for structured output (no JSON parsing), mirroring the
claim extractor. Supplementary and best-effort: on any failure it returns an
unavailable result and the rest of the analysis is unaffected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import anthropic

from config import settings


def period_end_label(report_date: str, filing_date: str = "") -> str:
    """Unambiguous period-end label from an ISO date, e.g. 'Mar 2026'."""
    src = report_date or filing_date
    try:
        return date.fromisoformat(src).strftime("%b %Y")
    except (ValueError, TypeError):
        return src[:7] if src else "prior period"

# Sonnet pricing (per million tokens), matching claim_extractor.
_INPUT_COST_PER_M = 3.00
_OUTPUT_COST_PER_M = 15.00

_KINDS = ("walked_back", "dropped", "escalated", "reversed", "new")


@dataclass
class ClaimDriftItem:
    """A single detected shift in the company's stated claims."""

    kind: str      # one of _KINDS
    label: str
    then: str      # what the prior filing asserted
    now: str       # what the current filing asserts ("—" for dropped claims)
    significance: str
    quote: str = ""  # verbatim supporting quote


@dataclass
class ClaimDriftResult:
    """How the company's stated claims shifted between two filings."""

    comparison_basis: str = ""   # e.g. "year-ago quarter"
    current_form: str = ""
    current_period: str = ""
    prior_period: str = ""
    headline: str = ""
    items: list[ClaimDriftItem] = field(default_factory=list)
    cost_usd: float = 0.0
    error: Optional[str] = None
    available: bool = False

    @property
    def counts(self) -> dict[str, int]:
        """Return the number of shifts of each kind."""
        tally = {k: 0 for k in _KINDS}
        for item in self.items:
            if item.kind in tally:
                tally[item.kind] += 1
        return tally


_DRIFT_TOOL = {
    "name": "report_claim_drift",
    "description": (
        "Report how the company's stated claims changed from the PRIOR filing "
        "to the CURRENT filing. Only report material, well-supported shifts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "One plain-English sentence summarizing the most important shifts in the company's narrative.",
            },
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": list(_KINDS),
                            "description": (
                                "walked_back = a quantitative/comparative claim whose figure weakened; "
                                "dropped = a claim asserted before but absent now; "
                                "escalated = a claim strengthened or given more prominence; "
                                "reversed = a claim that flipped direction; "
                                "new = a materially new assertion."
                            ),
                        },
                        "label": {"type": "string", "description": "Short topic label for the claim."},
                        "then": {"type": "string", "description": "What the PRIOR filing asserted."},
                        "now": {"type": "string", "description": "What the CURRENT filing asserts. Use '—' if the claim was dropped."},
                        "significance": {"type": "string", "description": "1 sentence on why the shift matters to an analyst."},
                        "quote": {"type": "string", "description": "Verbatim supporting quote (from CURRENT filing, or PRIOR for dropped/walked_back). Empty string if none."},
                    },
                    "required": ["kind", "label", "then", "now", "significance", "quote"],
                },
            },
        },
        "required": ["headline", "changes"],
    },
}

_SYSTEM_PROMPT = """You are a buy-side equity analyst who reads a company's SEC filings across periods and reports how the company's OWN stated claims about itself have shifted. You compare the earlier ("PRIOR") filing's MD&A to the newer ("CURRENT") filing's MD&A.

You focus on the company's assertions about growth, market position, product, execution, and unit economics — and how those assertions changed:
- walked_back: a quantitative or comparative claim whose figure or strength weakened (e.g. "growth of 40%" -> "growth of 20%").
- dropped: a specific claim the company asserted in PRIOR but no longer states in CURRENT. The omission itself is the signal.
- escalated: a claim strengthened, quantified upward, or given materially more prominence.
- reversed: a claim that flipped direction (e.g. from expansion to contraction).
- new: a materially new assertion not present before.

Rules you MUST follow:
1. Report ONLY material shifts an analyst tracking management credibility would care about. Ignore boilerplate and routine restatements. If nothing material shifted, return an empty changes array.
2. Ground every change in both texts. Never invent a shift. Provide a verbatim quote where one exists; otherwise leave quote empty rather than fabricating.
3. For "then" and "now", state the specific claim each filing made (use "—" for the missing side of a dropped or new claim).
4. Be concise. Return at most 8 changes, most significant first."""

_USER_TEMPLATE = """Compare the MD&A narratives below for {company_name} and report how the company's stated claims shifted from the PRIOR filing to the CURRENT filing.

PRIOR filing: {prior_label}
CURRENT filing: {current_label}

--- PRIOR FILING MD&A ---
{prior_text}

--- CURRENT FILING MD&A ---
{current_text}"""


def detect_claim_drift(
    current_text: str,
    prior_text: str,
    company_name: str,
    basis: str,
    current_form: str,
    current_label: str,
    prior_label: str,
) -> ClaimDriftResult:
    """Diff two MD&A narratives and return a structured claim-drift result.

    Returns a result with available=False on any error, so the caller can treat
    claim drift as best-effort without risking the rest of the analysis.
    """
    result = ClaimDriftResult(
        comparison_basis=basis,
        current_form=current_form,
        current_period=current_label,
        prior_period=prior_label,
    )
    if not current_text or not prior_text:
        return result

    user_prompt = _USER_TEMPLATE.format(
        company_name=company_name,
        prior_label=prior_label,
        current_label=current_label,
        prior_text=prior_text,
        current_text=current_text,
    )

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=8192,
            system=_SYSTEM_PROMPT,
            tools=[_DRIFT_TOOL],
            tool_choice={"type": "tool", "name": "report_claim_drift"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        result.error = str(exc)
        return result

    result.cost_usd = _estimate_cost(response.usage)
    for block in response.content:
        if block.type != "tool_use" or block.name != "report_claim_drift":
            continue
        data = block.input if isinstance(block.input, dict) else {}
        result.headline = data.get("headline", "") if isinstance(data.get("headline"), str) else ""
        items: list[ClaimDriftItem] = []
        changes = data.get("changes", [])
        if not isinstance(changes, list):
            changes = []
        for c in changes:
            if not isinstance(c, dict):
                continue  # model occasionally emits a stray string instead of an object
            kind = str(c.get("kind", "")).lower().strip()
            if kind not in _KINDS or not c.get("label"):
                continue
            items.append(
                ClaimDriftItem(
                    kind=kind,
                    label=c.get("label", ""),
                    then=c.get("then", ""),
                    now=c.get("now", ""),
                    significance=c.get("significance", ""),
                    quote=c.get("quote", ""),
                )
            )
        result.items = items
        result.available = True
        break

    return result


def _estimate_cost(usage: anthropic.types.Usage) -> float:
    input_cost = (usage.input_tokens / 1_000_000) * _INPUT_COST_PER_M
    output_cost = (usage.output_tokens / 1_000_000) * _OUTPUT_COST_PER_M
    return round(input_cost + output_cost, 6)
