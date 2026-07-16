"""Cached sample stress tests — real pipeline runs stored as JSON fixtures.

Samples are generated offline with generate_samples.py and loaded instantly in
the app, so first-time visitors see a complete claim-by-claim result without
waiting on (or paying for) a live run.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path

from pipeline.claim_drift import ClaimDriftItem, ClaimDriftResult
from pipeline.orchestrator import AnalysisResult
from schema.models import Analysis, Claim, ClaimVerdictModel, Evidence, Signal

SAMPLES_DIR = Path(__file__).parent / "sample_data"
MANIFEST_PATH = SAMPLES_DIR / "manifest.json"


def list_samples() -> list[dict]:
    """Ordered sample metadata from the manifest, filtered to fixtures present.

    Each entry: {"slug", "label", "ticker", "generated_on"}. The curator owns
    the manifest; the app only reads it, so add/remove is a data operation.
    """
    if MANIFEST_PATH.exists():
        data = json.loads(MANIFEST_PATH.read_text())
        return [s for s in data.get("samples", []) if sample_available(s["slug"])]
    return [
        {"slug": p.stem, "label": p.stem.title(), "ticker": "", "generated_on": ""}
        for p in sorted(SAMPLES_DIR.glob("*.json"))
        if p.name != "manifest.json"
    ]


def write_manifest(samples: list[dict]) -> None:
    """Persist the featured-sample lineup (used by the curator)."""
    MANIFEST_PATH.write_text(
        json.dumps({"updated": date.today().isoformat(), "samples": samples}, indent=1)
    )


def save_sample(slug: str, result: AnalysisResult) -> Path:
    payload = {
        "generated_on": date.today().isoformat(),
        "analysis": result.analysis.model_dump(mode="json"),
        "claims": [c.model_dump(mode="json") for c in result.claims],
        "verdicts": {k: v.model_dump(mode="json") for k, v in result.verdicts.items()},
        "evidences": {
            k: [e.model_dump(mode="json") for e in evs]
            for k, evs in result.evidences.items()
        },
        "signals": [s.model_dump(mode="json") for s in result.signals],
        "coverage": result.coverage,
        "errors": result.errors,
        "claim_drift": dataclasses.asdict(result.claim_drift) if result.claim_drift else None,
    }
    SAMPLES_DIR.mkdir(exist_ok=True)
    path = SAMPLES_DIR / f"{slug}.json"
    path.write_text(json.dumps(payload, indent=1))
    return path


def sample_available(slug: str) -> bool:
    return (SAMPLES_DIR / f"{slug}.json").exists()


def load_sample(slug: str) -> tuple[AnalysisResult, str]:
    """Load a fixture; returns (result, generated_on_iso_date)."""
    d = json.loads((SAMPLES_DIR / f"{slug}.json").read_text())

    claim_drift = None
    if d.get("claim_drift"):
        cd = dict(d["claim_drift"])
        cd["items"] = [ClaimDriftItem(**i) for i in cd.get("items", [])]
        claim_drift = ClaimDriftResult(**cd)

    result = AnalysisResult(
        analysis=Analysis.model_validate(d["analysis"]),
        claims=[Claim.model_validate(c) for c in d["claims"]],
        verdicts={
            k: ClaimVerdictModel.model_validate(v) for k, v in d["verdicts"].items()
        },
        evidences={
            k: [Evidence.model_validate(e) for e in evs]
            for k, evs in d["evidences"].items()
        },
        signals=[Signal.model_validate(s) for s in d["signals"]],
        coverage=d["coverage"],
        errors=d.get("errors", []),
        claim_drift=claim_drift,
    )
    return result, d["generated_on"]
