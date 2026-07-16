"""Regenerate the cached sample stress tests (sample_data/*.json).

Runs the real company-name-mode pipeline for each sample company and stores
the result as a JSON fixture. Costs a few live API calls per company — run
occasionally, then commit the updated JSON.

Usage:  venv/bin/python generate_samples.py [slug ...]
        (no args = regenerate all samples)
"""
import sys

from dotenv import load_dotenv

load_dotenv()

from pipeline.orchestrator import run_analysis
from samples import list_samples, save_sample
from schema.enums import CompanyType, InputType
from schema.models import Company
from utils.company_lookup import lookup_cik


def generate(slug: str, name: str, domain: str = "") -> None:
    print(f"── {slug}: resolving {name!r}…")
    cik, ticker = lookup_cik(name)
    company = Company(
        entity_id=name.lower().replace(" ", "_"),
        name=name,
        ticker=ticker,
        cik=cik,
        domain=domain or f"{slug}.com",
        company_type=CompanyType.public,
    )
    print("   running full pipeline (company-name mode)…")
    result = run_analysis(
        company=company,
        input_text=None,
        input_type=InputType.company_name,
        progress_callback=lambda label, pct: print(f"   [{pct:4.0%}] {label}"),
    )
    path = save_sample(slug, result)
    print(f"   saved {path.name}: {len(result.claims)} claims, "
          f"{len(result.verdicts)} verdicts, {len(result.signals)} signals, "
          f"drift={'yes' if result.claim_drift and result.claim_drift.available else 'no'}")


if __name__ == "__main__":
    lineup = {s["slug"]: s for s in list_samples()}
    slugs = sys.argv[1:] or list(lineup)
    for slug in slugs:
        s = lineup[slug]
        generate(slug, s.get("ticker") or s["label"])
