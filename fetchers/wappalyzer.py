"""
Wappalyzer OSS tech stack fetcher.
Runs Wappalyzer CLI as a Node.js subprocess against the company domain.
Returns:
  - tech_stack: detected technologies grouped by category

Requires Node.js and @wappalyzer/cli installed:
  npm install -g @wappalyzer/cli
"""
from __future__ import annotations

import json
import subprocess

from fetchers.base import BaseFetcher
from schema.enums import DataSource, SignalType
from schema.models import Company, Signal


class WappalyzerFetcher(BaseFetcher):

    def fetch(self, company: Company) -> list[Signal]:
        url = f"https://{company.domain}"
        result = self._run_wappalyzer(url)
        if not result:
            return []

        # Flatten technologies into a summary
        techs = result.get("technologies", [])
        if not techs:
            return []

        by_category: dict[str, list[str]] = {}
        for tech in techs:
            for cat in tech.get("categories", [{"name": "Other"}]):
                cat_name = cat.get("name", "Other")
                by_category.setdefault(cat_name, []).append(tech.get("name", ""))

        return [Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.tech_stack,
            signal_name="tech_stack_by_category",
            value=by_category,
            unit="dict",
            source=DataSource.wappalyzer,
            source_url=url,
            reliability_tier=3,
            raw={"tech_count": len(techs), "url": url},
        )]

    def _run_wappalyzer(self, url: str) -> dict | None:
        try:
            proc = subprocess.run(
                ["wappalyzer", url, "--pretty"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return None
            return json.loads(proc.stdout)
        except Exception:
            return None
