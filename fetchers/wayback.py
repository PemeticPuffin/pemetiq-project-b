"""
Wayback Machine CDX API fetcher.
Returns:
  - pricing_page_history: snapshot count and date range for pricing page

URL discovery: tries multiple candidate paths and uses whichever has snapshot history.
"""
from __future__ import annotations

from datetime import date

from fetchers.base import BaseFetcher
from schema.enums import DataSource, SignalType
from schema.models import Company, Signal

_CDX_URL = "http://web.archive.org/cdx/search/cdx"

# Candidate pricing paths — tried in order, first with results wins
_PRICING_PATHS = [
    "/pricing",
    "/pricing/",
    "/editions-pricing",
    "/plans",
    "/plans-pricing",
    "/pricing-plans",
]


class WaybackFetcher(BaseFetcher):

    def fetch(self, company: Company) -> list[Signal]:
        signals: list[Signal] = []

        pricing = self._fetch_pricing_history(company)
        if pricing:
            signals.append(pricing)

        return signals

    def _fetch_pricing_history(self, company: Company) -> Signal | None:
        domain = company.domain

        for path in _PRICING_PATHS:
            url = f"https://{domain}{path}"
            result = self._query_cdx(url)
            if result:
                snapshots, first_date, last_date = result
                return Signal(
                    entity_id=company.entity_id,
                    signal_type=SignalType.pricing_page_history,
                    signal_name="pricing_page_snapshot_count",
                    value=snapshots,
                    unit="count",
                    period_start=first_date,
                    period_end=last_date,
                    source=DataSource.wayback_cdx,
                    source_url=f"https://web.archive.org/web/*/{url}",
                    reliability_tier=3,
                    raw={"path_matched": path, "domain": domain},
                )

        return None

    def _query_cdx(self, url: str) -> tuple[int, date | None, date | None] | None:
        params = {
            "url": url,
            "output": "json",
            "fl": "timestamp",
            "collapse": "timestamp:8",  # deduplicate by day
            "limit": "100",
        }
        try:
            data = self.get_json(_CDX_URL, params=params, timeout=20)
        except Exception:
            return None

        if not isinstance(data, list) or len(data) <= 1:
            return None

        # First row is header ["timestamp"]
        rows = data[1:]
        if not rows:
            return None

        timestamps = [r[0] for r in rows if r]
        timestamps.sort()

        def parse_ts(ts: str) -> date | None:
            try:
                from datetime import datetime
                return datetime.strptime(ts[:8], "%Y%m%d").date()
            except Exception:
                return None

        first = parse_ts(timestamps[0])
        last = parse_ts(timestamps[-1])
        return len(rows), first, last
