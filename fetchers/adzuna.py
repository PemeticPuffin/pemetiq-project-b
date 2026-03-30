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
            total_count, results = self._search_jobs(company.name)
        except Exception:
            return []

        if not results:
            return []

        signals: list[Signal] = []

        # Total hiring volume — use API's reported total, not len(results)
        signals.append(Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.hiring_volume,
            signal_name="open_jobs_count",
            value=total_count,
            unit="count",
            period_end=date.today(),
            source=DataSource.adzuna,
            source_url=f"https://www.adzuna.com/search?q={company.name.replace(' ', '+')}",
            reliability_tier=2,
            raw={"query": company.name, "total_count": total_count, "sample_size": len(results)},
        ))

        # Hiring mix — run across the full paginated sample for reliable percentages
        titles = [r.get("title", "") for r in results]
        ai_ml = sum(1 for t in titles if _AI_ML_KEYWORDS.search(t))
        eng   = sum(1 for t in titles if _ENGINEERING_KEYWORDS.search(t))
        sales = sum(1 for t in titles if _SALES_KEYWORDS.search(t))
        total = len(titles)

        signals.append(Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.hiring_mix,
            signal_name="hiring_mix_breakdown",
            value={
                "ai_ml_pct":        round(ai_ml / total * 100, 1) if total else 0,
                "engineering_pct":  round(eng   / total * 100, 1) if total else 0,
                "sales_pct":        round(sales  / total * 100, 1) if total else 0,
                "ai_ml_count":      ai_ml,
                "engineering_count": eng,
                "sales_count":      sales,
                "sample_size":      total,
            },
            unit="pct_breakdown",
            period_end=date.today(),
            source=DataSource.adzuna,
            reliability_tier=2,
            raw={"sample_titles": titles[:20]},
        ))

        return signals

    def _search_jobs(self, company_name: str) -> tuple[int, list[dict]]:
        """
        Fetch up to 3 pages of results (150 jobs) for a reliable hiring mix sample.
        Returns (total_count_from_api, sampled_results).
        total_count is the API's reported total — accurate regardless of pagination.
        """
        base_params = {
            "app_id": settings.ADZUNA_APP_ID,
            "app_key": settings.ADZUNA_APP_KEY,
            "results_per_page": 50,
            "what_or": company_name,
            "content-type": "application/json",
        }

        all_results: list[dict] = []
        total_count = 0

        for page in range(1, 4):  # pages 1, 2, 3
            data = self.get_json(f"{_BASE}/search/{page}", params=base_params, timeout=15)
            if not isinstance(data, dict):
                break
            if page == 1:
                total_count = data.get("count", 0)
            page_results = data.get("results", [])
            if not page_results:
                break
            all_results.extend(page_results)
            # No point fetching more pages than exist
            if len(all_results) >= total_count:
                break

        return total_count, all_results
