"""
Apple App Store fetcher via iTunes Search API (no key required).
Returns:
  - app_store_rating: average rating and review count for top app
  - mobile_ratings: all apps found (for multi-app companies)
"""
from __future__ import annotations

from fetchers.base import BaseFetcher
from schema.enums import DataSource, SignalType
from schema.models import Company, Signal

_SEARCH_URL = "https://itunes.apple.com/search"


class AppStoreFetcher(BaseFetcher):

    def fetch(self, company: Company) -> list[Signal]:
        try:
            results = self._search(company.name)
        except Exception:
            return []

        if not results:
            return []

        signals: list[Signal] = []

        # Primary signal: top app (most reviews)
        top = max(results, key=lambda r: r.get("userRatingCount", 0))
        signals.append(Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.app_store_rating,
            signal_name="appstore_rating_top_app",
            value=round(top.get("averageUserRating", 0), 2),
            unit="rating_5",
            source=DataSource.apple_appstore,
            source_url=top.get("trackViewUrl"),
            reliability_tier=2,
            raw={
                "app_name": top.get("trackName"),
                "review_count": top.get("userRatingCount"),
                "bundle_id": top.get("bundleId"),
            },
        ))

        # Secondary: all apps found (max 5) for mobile presence breadth
        for app in results[:5]:
            signals.append(Signal(
                entity_id=company.entity_id,
                signal_type=SignalType.mobile_ratings,
                signal_name=f"appstore_app_{app.get('bundleId', 'unknown').replace('.', '_')}",
                value=round(app.get("averageUserRating", 0), 2),
                unit="rating_5",
                source=DataSource.apple_appstore,
                source_url=app.get("trackViewUrl"),
                reliability_tier=2,
                raw={
                    "app_name": app.get("trackName"),
                    "review_count": app.get("userRatingCount"),
                },
            ))

        return signals

    def _search(self, company_name: str) -> list[dict]:
        params = {
            "term": company_name,
            "entity": "software",
            "limit": 10,
            "country": "us",
        }
        data = self.get_json(_SEARCH_URL, params=params, timeout=10)
        if not isinstance(data, dict):
            return []
        results = data.get("results", [])
        # Meaningful tokens from the company name (skip short words like "the", "of")
        tokens = [w.lower() for w in company_name.split() if len(w) > 2]
        return [
            r for r in results
            if r.get("averageUserRating")
            and r.get("userRatingCount", 0) > 100
            and self._is_relevant(r, tokens)
        ]

    @staticmethod
    def _is_relevant(app: dict, tokens: list[str]) -> bool:
        """Return True if the app plausibly belongs to the queried company."""
        if not tokens:
            return True
        haystack = " ".join([
            app.get("trackName", ""),
            app.get("artistName", ""),
            app.get("bundleId", ""),
        ]).lower()
        return any(token in haystack for token in tokens)
