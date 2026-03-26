"""
Tests for edgar.py helper functions and EdgarFetcher.

Helper functions (_parse_date, _is_annual_period, _extract_mda_section,
_pick_document) are pure logic — no mocks. EdgarFetcher.fetch() is tested
with mocked HTTP responses.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from datetime import date

import pytest

from fetchers.edgar import (
    EdgarFetcher,
    _extract_mda_section,
    _is_annual_period,
    _parse_date,
    _pick_document,
)
from schema.enums import CompanyType, SignalType
from schema.models import Company


# ── _parse_date ───────────────────────────────────────────────────────────────

def test_parse_date_valid():
    assert _parse_date("2025-01-31") == date(2025, 1, 31)


def test_parse_date_none():
    assert _parse_date(None) is None


def test_parse_date_empty_string():
    assert _parse_date("") is None


def test_parse_date_invalid_format():
    assert _parse_date("31/01/2025") is None


# ── _is_annual_period ─────────────────────────────────────────────────────────

def test_is_annual_period_true():
    assert _is_annual_period("2024-02-01", "2025-01-31") is True


def test_is_annual_period_false_quarterly():
    assert _is_annual_period("2024-11-01", "2025-01-31") is False


def test_is_annual_period_none_start():
    assert _is_annual_period(None, "2025-01-31") is False


def test_is_annual_period_none_end():
    assert _is_annual_period("2024-01-31", None) is False


def test_is_annual_period_boundary():
    # Exactly 300 days → annual
    assert _is_annual_period("2024-03-06", "2025-01-01") is True  # ~300 days


# ── _extract_mda_section ──────────────────────────────────────────────────────

def test_extract_mda_section_finds_marker():
    body = "Table of Contents ... Management's Discussion and Analysis ... page 42 " + \
           " " * 5000 + \
           "Management's Discussion and Analysis of Financial Condition " + \
           "Revenue increased 20% year-over-year driven by strong cloud adoption."
    result = _extract_mda_section(body, max_chars=500)
    assert "Revenue increased 20%" in result


def test_extract_mda_section_no_marker_falls_back():
    """No MD&A marker → skips first 25% of doc."""
    # 400 chars: first 100 (25%) are "A", remaining 300 are "B"
    body = "A" * 100 + "B" * 300
    result = _extract_mda_section(body, max_chars=200)
    # start = 400 // 4 = 100, which is the first "B"
    assert result.startswith("B")


def test_extract_mda_section_appends_ellipsis_when_truncated():
    body = "Management's Discussion and Analysis " + "X" * 2000
    result = _extract_mda_section(body, max_chars=100)
    assert result.endswith("…")


def test_extract_mda_section_no_ellipsis_when_fits():
    body = "Management's Discussion and Analysis " + "X" * 50
    result = _extract_mda_section(body, max_chars=10000)
    assert not result.endswith("…")


# ── _pick_document ────────────────────────────────────────────────────────────

def test_pick_document_10k_primary_doc():
    result = _pick_document("10-K", "crm-20250131.htm", ["crm-20250131.htm", "ex31.htm"])
    assert result == "crm-20250131.htm"


def test_pick_document_10k_fallback_to_largest_htm():
    result = _pick_document("10-K", "missing.htm", ["ex31.htm", "annual-report.htm", "index.htm"])
    # index.htm is a support file; ex31.htm is a support file; annual-report.htm wins
    assert result == "annual-report.htm"


def test_pick_document_10k_no_htm():
    result = _pick_document("10-K", None, ["data.xml", "filing.xsd"])
    assert result is None


def test_pick_document_8k_prefers_ex991():
    result = _pick_document("8-K", "8k.htm", ["8k.htm", "ex991.htm", "ex311.htm"])
    assert result == "ex991.htm"


def test_pick_document_8k_fallback_to_any_htm():
    result = _pick_document("8-K", "8k.htm", ["8k.htm", "index.htm"])
    # index.htm is a support file, so 8k.htm should win
    assert result == "8k.htm"


def test_pick_document_unknown_form():
    result = _pick_document("SC 13G", None, ["filing.htm"])
    assert result is None


# ── EdgarFetcher.fetch() ──────────────────────────────────────────────────────

@pytest.fixture
def salesforce_company():
    return Company(
        entity_id="salesforce",
        name="Salesforce",
        ticker="CRM",
        cik="1108524",
        domain="salesforce.com",
        company_type=CompanyType.public,
    )


def test_edgar_fetcher_no_cik_returns_empty(private_company):
    """Companies without a CIK should return no signals."""
    fetcher = EdgarFetcher()
    signals = fetcher.fetch(private_company)
    assert signals == []


def _xbrl_facts(revenue: int, prior_revenue: int) -> dict:
    """Build a minimal XBRL companyfacts response with revenue data."""
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-K",
                                "start": "2023-02-01",
                                "end": "2024-01-31",
                                "val": prior_revenue,
                                "accn": "0001234-24-000001",
                            },
                            {
                                "form": "10-K",
                                "start": "2024-02-01",
                                "end": "2025-01-31",
                                "val": revenue,
                                "accn": "0001234-25-000001",
                            },
                        ]
                    }
                }
            }
        }
    }


@patch.object(EdgarFetcher, "get_json")
def test_edgar_fetcher_returns_revenue_signal(mock_get_json, salesforce_company):
    """EdgarFetcher returns annual_revenue and revenue_growth signals from XBRL."""
    mock_get_json.side_effect = [
        _xbrl_facts(36_000_000_000, 30_000_000_000),  # companyfacts call
        {"filings": {"recent": {"form": [], "filingDate": [], "accessionNumber": []}}},  # submissions call
    ]

    fetcher = EdgarFetcher()
    signals = fetcher.fetch(salesforce_company)

    signal_types = {s.signal_type for s in signals}
    assert SignalType.annual_revenue in signal_types
    assert SignalType.revenue_growth in signal_types


@patch.object(EdgarFetcher, "get_json")
def test_edgar_fetcher_handles_http_error(mock_get_json, salesforce_company):
    """HTTP error on XBRL call → returns empty list (doesn't crash)."""
    mock_get_json.side_effect = Exception("HTTP 503")
    signals = EdgarFetcher().fetch(salesforce_company)
    assert signals == []


@patch.object(EdgarFetcher, "get_json")
def test_edgar_fetcher_returns_8k_count(mock_get_json, salesforce_company):
    """8-K count signal is returned when recent 8-Ks exist."""
    from datetime import date as _date
    cutoff_year = "2025"
    mock_get_json.side_effect = [
        _xbrl_facts(36_000_000_000, 30_000_000_000),
        {
            "filings": {
                "recent": {
                    "form": ["8-K", "8-K", "10-Q"],
                    "filingDate": [f"{cutoff_year}-06-01", f"{cutoff_year}-09-01", f"{cutoff_year}-07-01"],
                    "accessionNumber": ["0001-25-001", "0001-25-002", "0001-25-003"],
                }
            }
        },
    ]
    signals = EdgarFetcher().fetch(salesforce_company)
    signal_types = {s.signal_type for s in signals}
    assert SignalType.filing_language_change in signal_types
