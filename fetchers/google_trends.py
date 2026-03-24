"""
Google Trends fetcher via pytrends.
Returns:
  - search_momentum: 52-week average interest (0–100 index)
  - search_share_vs_competitors: relative interest vs up to 4 competitors
"""
from __future__ import annotations

import warnings
from datetime import date, timedelta

from fetchers.base import BaseFetcher
from schema.enums import DataSource, SignalType
from schema.models import Company, Signal

# Suppress pytrends pandas FutureWarning (pandas 2.x compat issue)
warnings.filterwarnings("ignore", category=FutureWarning, module="pytrends")

_COMPETITORS_DEFAULT = 4  # Google Trends max is 5 terms including the company itself


class GoogleTrendsFetcher(BaseFetcher):

    def fetch(self, company: Company, competitors: list[str] | None = None) -> list[Signal]:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            return []

        pytrends = TrendReq(hl="en-US", tz=360)
        signals: list[Signal] = []

        # 52-week momentum
        momentum = self._fetch_momentum(pytrends, company)
        if momentum:
            signals.append(momentum)

        # Competitive share (optional — only if competitors provided)
        if competitors:
            share = self._fetch_share(pytrends, company, competitors[:_COMPETITORS_DEFAULT])
            signals.extend(share)

        return signals

    def _fetch_momentum(self, pytrends, company: Company) -> Signal | None:
        try:
            pytrends.build_payload([company.name], timeframe="today 12-m", geo="")
            df = pytrends.interest_over_time()
            if df.empty or company.name not in df.columns:
                return None
            avg = round(float(df[company.name].mean()), 1)
            today = date.today()
            return Signal(
                entity_id=company.entity_id,
                signal_type=SignalType.search_momentum,
                signal_name="search_interest_52wk_avg",
                value=avg,
                unit="index_0-100",
                period_start=today - timedelta(weeks=52),
                period_end=today,
                source=DataSource.google_trends,
                source_url="https://trends.google.com",
                reliability_tier=2,
                raw={"weekly_points": len(df)},
            )
        except Exception:
            return None

    def _fetch_share(self, pytrends, company: Company, competitors: list[str]) -> list[Signal]:
        keywords = [company.name] + competitors
        try:
            pytrends.build_payload(keywords, timeframe="today 12-m", geo="")
            df = pytrends.interest_over_time()
            if df.empty:
                return []
        except Exception:
            return []

        signals: list[Signal] = []
        today = date.today()
        for kw in keywords:
            if kw not in df.columns:
                continue
            avg = round(float(df[kw].mean()), 1)
            signals.append(Signal(
                entity_id=company.entity_id,
                signal_type=SignalType.search_share_vs_competitors,
                signal_name=f"search_interest_vs_{kw.lower().replace(' ', '_')}",
                value=avg,
                unit="index_0-100",
                period_start=today - timedelta(weeks=52),
                period_end=today,
                source=DataSource.google_trends,
                source_url="https://trends.google.com",
                reliability_tier=2,
                raw={"keyword": kw, "compared_to": competitors},
            ))
        return signals
