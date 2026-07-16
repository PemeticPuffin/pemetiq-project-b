"""Autonomous sample-lineup curator for Manseil.

Monthly (via GitHub Actions) this:
  1. Asks Claude — grounded with web search — which public US companies have the
     most demo-worthy narratives to STRESS-TEST right now (bold, contestable
     claims where the tool produces interesting verdicts), given the currently
     featured set and with hysteresis so the lineup evolves rather than thrashes.
  2. Validates each pick resolves to a US public company on SEC EDGAR.
  3. Runs the real pipeline for newly chosen companies and QUALITY-GATES each —
     a sample is only published if it has enough claims, available claim-drift,
     and at least a couple of decisive verdicts (Supported / Partially / Contested)
     so we never feature a flat, all-"insufficient-evidence" run (the reason
     Gartner was a weak sample). Surviving incumbents are kept as-is.
  4. Updates sample_data/manifest.json + fixtures and writes curation_summary.md
     (used as the pull-request body).

Nothing here publishes to the live site: the GitHub Actions workflow opens a
pull request with the changes for Aaron to approve.

Usage:
    python curate_samples.py            # full run
    python curate_samples.py --dry-run  # selection only
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()

from config.settings import ANTHROPIC_MODEL
from generate_samples import generate
from samples import SAMPLES_DIR, list_samples, load_sample, write_manifest
from utils.company_lookup import lookup_cik

TARGET_SIZE = 2
MAX_SWAPS = 1
_DECISIVE = {"supported", "partially_supported", "contested"}

SELECTOR_SYSTEM = """You curate the sample companies featured on Manseil, a narrative stress-test tool for \
skeptical investors and analysts. Each sample extracts a company's stated claims (from its latest SEC \
filing) and tests them claim-by-claim against public signals, returning verdicts (Supported / Partially \
Supported / Contested / Insufficient Evidence / Not Testable) plus a year-over-year claim-drift read on \
whether management is walking back its own narrative.

Your job: choose the public US companies whose narratives are the most compelling to STRESS-TEST right now \
for that audience — names with bold, contestable, heavily-scrutinized stories (aggressive growth or margin \
claims, AI/turnaround narratives, valuation debates) where the tool will surface something sharp.

Hard constraints on every pick:
- US-listed company that files with the SEC (10-K / 10-Q). No foreign private issuers, funds, or SPACs.
- At least ~1 year of filing history (the tool compares against the year-ago quarter); avoid very recent IPOs.
- Favor variety across sectors and avoid two companies with near-identical stories.
- Prefer companies whose filings contain quantitative, testable claims (revenue growth, margins, retention) \
over vague qualitative ones.

Use web search to ground your choices in what is actually happening in the market as of today.

Apply hysteresis: KEEP currently featured companies that are still highly relevant; change at most the number \
of slots you are told is allowed. If the current lineup is still great, change nothing.

Respond with ONLY a JSON object, no prose:
{"lineup": [{"ticker": "TICK", "label": "Short Name", "reason": "one sentence on why it's a timely stress test"}],
 "summary": "2-3 sentences explaining what changed vs the current lineup and why"}"""


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _extract_json(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def select_lineup(current: list[dict]) -> dict:
    current_desc = ", ".join(f"{s['label']} ({s.get('ticker','?')})" for s in current) or "(none)"
    user = (
        f"Today is {datetime.date.today():%B %d, %Y}.\n"
        f"Currently featured ({len(current)}): {current_desc}.\n"
        f"Choose the ideal {TARGET_SIZE}-company lineup. You may change at most {MAX_SWAPS} "
        f"of the current picks."
    )
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=SELECTOR_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = next((b.text for b in reversed(resp.content) if b.type == "text"), "")
    data = json.loads(_extract_json(text))
    data["lineup"] = data["lineup"][:TARGET_SIZE]
    return data


def _reconcile(lineup: list[dict], current: list[dict]) -> None:
    by_ticker = {s.get("ticker", "").upper(): s for s in current if s.get("ticker")}
    for item in lineup:
        inc = by_ticker.get(item.get("ticker", "").upper())
        if inc:
            item["slug"] = inc["slug"]
            item["label"] = inc["label"]
            item["generated_on"] = inc.get("generated_on", "")
            item["is_incumbent"] = True
        else:
            item["slug"] = _slug(item["label"])
            item["is_incumbent"] = False


def quality_ok(slug: str) -> bool:
    try:
        result, _ = load_sample(slug)
    except Exception:
        return False
    drift_ok = bool(result.claim_drift and result.claim_drift.available)
    decisive = sum(1 for v in result.verdicts.values() if v.verdict.value in _DECISIVE)
    return len(result.claims) >= 6 and drift_ok and decisive >= 2


def _validate(item: dict) -> bool:
    cik, _ = lookup_cik(item["label"])
    return cik is not None


def _generate_gated(slug: str, name: str) -> bool:
    for attempt in (1, 2):
        try:
            generate(slug, name)
        except Exception as exc:
            print(f"    generation attempt {attempt} errored: {exc}")
            continue
        if quality_ok(slug):
            return True
        print(f"    attempt {attempt}: incomplete/flat, retrying…")
    (SAMPLES_DIR / f"{slug}.json").unlink(missing_ok=True)
    return False


def _manifest_entry(item: dict) -> dict:
    return {
        "slug": item["slug"],
        "label": item["label"],
        "ticker": item["ticker"],
        "generated_on": item.get("generated_on") or datetime.date.today().isoformat(),
    }


def _prune_dropped(keep_slugs: set[str]) -> None:
    for p in SAMPLES_DIR.glob("*.json"):
        if p.name != "manifest.json" and p.stem not in keep_slugs:
            print(f"  removing dropped sample: {p.name}")
            p.unlink()


def _write_summary(before: list[dict], after: list[dict], rationale: str) -> None:
    before_s = {s["slug"] for s in before}
    after_s = {s["slug"] for s in after}
    added = [s for s in after if s["slug"] not in before_s]
    removed = [s for s in before if s["slug"] not in after_s]
    lines = ["## Monthly sample-lineup update", "", rationale, ""]
    if added:
        lines.append("**Added:** " + ", ".join(f"{s['label']} ({s['ticker']})" for s in added))
    if removed:
        lines.append("**Removed:** " + ", ".join(s["label"] for s in removed))
    if not added and not removed:
        lines.append("_No changes — current lineup is still the most relevant._")
    lines += ["", "**Featured after this update:** "
              + ", ".join(f"{s['label']} ({s['ticker']})" for s in after)]
    (SAMPLES_DIR.parent / "curation_summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Select only; do not run the pipeline or change files.")
    args = ap.parse_args()

    current = list_samples()
    print(f"Current lineup: {[s['label'] for s in current]}")

    picked = select_lineup(current)
    _reconcile(picked["lineup"], current)
    print("\nProposed lineup:")
    for item in picked["lineup"]:
        flag = "keep" if item["is_incumbent"] else "NEW"
        print(f"  [{flag}] {item['label']} ({item['ticker']}) — {item['reason']}")
    print(f"\nRationale: {picked['summary']}")

    if args.dry_run:
        print("\n(dry run — no files changed)")
        return

    final: list[dict] = []
    for item in picked["lineup"]:
        slug = item["slug"]
        if item["is_incumbent"] and quality_ok(slug):
            final.append(_manifest_entry(item))
            continue
        if not _validate(item):
            print(f"  ✗ {item['label']}: failed EDGAR validation — skipped")
            continue
        if _generate_gated(slug, item["label"]):
            item["generated_on"] = datetime.date.today().isoformat()
            final.append(_manifest_entry(item))
        else:
            print(f"  ✗ {item['label']}: failed quality gate after retry — skipped")

    if len(final) < TARGET_SIZE:
        for s in current:
            if len(final) >= TARGET_SIZE:
                break
            if s["slug"] not in {f["slug"] for f in final} and quality_ok(s["slug"]):
                final.append(s)

    if [f["slug"] for f in final] == [s["slug"] for s in current]:
        print("\nNo change — current lineup is still the most relevant. Nothing to propose.")
        return

    _prune_dropped({f["slug"] for f in final})
    write_manifest(final)
    _write_summary(current, final, picked["summary"])
    print(f"\nFinal lineup: {[f['label'] for f in final]}")


if __name__ == "__main__":
    main()
