"""
GDELT async fetcher — news volume and press sentiment.
MUST be run as a background task (14s+ latency).

Returns:
  - news_volume: article count matching company name in title (last 12 months)

Implementation requirements (from Phase 2 validation):
  1. Title-match filter mandatory — raw query returns too many tangential mentions
  2. Always async — cannot block the UI critical path
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import aiohttp

from schema.enums import DataSource, SignalType
from schema.models import Company, Signal

_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"


async def fetch_gdelt(company: Company) -> list[Signal]:
    """
    Async entrypoint — await this in a background task.
    Usage in orchestrator:
        gdelt_task = asyncio.create_task(fetch_gdelt(company))
        # ... run other fetchers ...
        gdelt_signals = await gdelt_task
    """
    query = f'"{company.name}"'  # title-match filter applied via domain search
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": "250",
        "timespan": "12m",
        "format": "json",
        "sort": "DateDesc",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(_BASE, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
    except (asyncio.TimeoutError, aiohttp.ClientError, Exception):
        return []

    articles = data.get("articles", [])
    if not articles:
        return []

    # Title-match filter: only articles where company name appears in title
    company_lower = company.name.lower()
    matched = [
        a for a in articles
        if company_lower in a.get("title", "").lower()
    ]

    if not matched:
        return []

    today = date.today()
    return [Signal(
        entity_id=company.entity_id,
        signal_type=SignalType.news_volume,
        signal_name="gdelt_title_match_count_12mo",
        value=len(matched),
        unit="count",
        period_start=today - timedelta(days=365),
        period_end=today,
        source=DataSource.gdelt,
        source_url="https://api.gdeltproject.org",
        reliability_tier=3,
        raw={
            "total_returned": len(articles),
            "title_matched": len(matched),
            "sample_titles": [a.get("title") for a in matched[:5]],
        },
    )]
