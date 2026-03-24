"""
Adzuna job postings fetcher.
Returns:
  - hiring_volume: total open job count
  - hiring_mix: breakdown of technical vs. non-technical roles (proxy for AI/ML claims)

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY env vars.
"""
from __future__ import annotations

import re
from datetime import date

from config import settings
from fetchers.base import BaseFetcher
from schema.enums import DataSource, SignalType
from schema.models import Company, Signal

_BASE = "https://api.adzuna.com/v1/api/jobs/us"

# Role categories for hiring mix analysis
_AI_ML_KEYWORDS = re.compile(
    r"\b(machine learning|ml engineer|data scientist|ai engineer|llm|nlp|"
    r"deep learning|computer vision|mlops|pytorch|tensorflow)\b",
    re.IGNORECASE,
)
_ENGINEERING_KEYWORDS = re.compile(
    r"\b(software engineer|backend|frontend|full.?stack|devops|platform engineer|"
    r"sre|data engineer|cloud engineer)\b",
    re.IGNORECASE,
)
_SALES_KEYWORDS = re.compile(
    r"\b(account executive|sales|business development|bdr|sdr|customer success)\b",
    re.IGNORECASE,
)


class AdzunaFetcher(BaseFetcher):

    def fetch(self, company: Company) -> list[Signal]:
        if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
            return []

        try:
            results = self._search_jobs(company.name)
        except Exception:
            return []

        if not results:
            return []

        signals: list[Signal] = []

        # Total hiring volume
        signals.append(Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.hiring_volume,
            signal_name="open_jobs_count",
            value=len(results),
            unit="count",
            period_end=date.today(),
            source=DataSource.adzuna,
            source_url=f"https://www.adzuna.com/search?q={company.name.replace(' ', '+')}",
            reliability_tier=2,
            raw={"query": company.name, "result_count": len(results)},
        ))

        # Hiring mix
        titles = [r.get("title", "") for r in results]
        ai_ml = sum(1 for t in titles if _AI_ML_KEYWORDS.search(t))
        eng = sum(1 for t in titles if _ENGINEERING_KEYWORDS.search(t))
        sales = sum(1 for t in titles if _SALES_KEYWORDS.search(t))
        total = len(titles)

        signals.append(Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.hiring_mix,
            signal_name="hiring_mix_breakdown",
            value={
                "ai_ml_pct": round(ai_ml / total * 100, 1) if total else 0,
                "engineering_pct": round(eng / total * 100, 1) if total else 0,
                "sales_pct": round(sales / total * 100, 1) if total else 0,
                "ai_ml_count": ai_ml,
                "engineering_count": eng,
                "sales_count": sales,
                "total": total,
            },
            unit="pct_breakdown",
            period_end=date.today(),
            source=DataSource.adzuna,
            reliability_tier=2,
            raw={"sample_titles": titles[:20]},
        ))

        return signals

    def _search_jobs(self, company_name: str) -> list[dict]:
        params = {
            "app_id": settings.ADZUNA_APP_ID,
            "app_key": settings.ADZUNA_APP_KEY,
            "results_per_page": 50,
            "what_or": company_name,
            "content-type": "application/json",
        }
        data = self.get_json(f"{_BASE}/search/1", params=params, timeout=15)
        if not isinstance(data, dict):
            return []
        return data.get("results", [])
