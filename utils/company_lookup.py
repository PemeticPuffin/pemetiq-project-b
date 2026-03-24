"""
EDGAR company lookup — resolves a company name to CIK + ticker.

Uses the EDGAR company tickers JSON (full public company list, no key required).
Falls back to fuzzy substring match if exact match fails.
"""
from __future__ import annotations

import re

import requests

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_HEADERS = {"User-Agent": "Pemetiq/ProjectB contact@pemetiq.com"}
_cache: dict | None = None


def lookup_cik(company_name: str) -> tuple[str | None, str | None]:
    """
    Search EDGAR for a company by name.

    Returns:
        (cik_str, ticker) — both None if not found
        cik_str is zero-padded to 10 digits
    """
    data = _load_tickers()
    if not data:
        return None, None

    name_lower = company_name.lower().strip()

    # Pass 1: exact title match
    for entry in data.values():
        if entry.get("title", "").lower() == name_lower:
            return str(entry["cik_str"]).zfill(10), entry.get("ticker")

    # Pass 2: ticker match (user may have entered "AAPL")
    ticker_upper = company_name.upper().strip()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10), entry.get("ticker")

    # Pass 3: substring match (first word of company name)
    first_word = re.split(r"[\s,.]", name_lower)[0]
    candidates = [
        entry for entry in data.values()
        if first_word in entry.get("title", "").lower()
    ]
    if len(candidates) == 1:
        return str(candidates[0]["cik_str"]).zfill(10), candidates[0].get("ticker")

    # Pass 4: pick the candidate whose title starts with the query (common for "Salesforce" → "Salesforce Inc")
    starts = [c for c in candidates if c.get("title", "").lower().startswith(name_lower)]
    if starts:
        return str(starts[0]["cik_str"]).zfill(10), starts[0].get("ticker")

    return None, None


def _load_tickers() -> dict | None:
    global _cache
    if _cache is not None:
        return _cache
    try:
        resp = requests.get(_TICKERS_URL, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        _cache = resp.json()
        return _cache
    except Exception:
        return None
