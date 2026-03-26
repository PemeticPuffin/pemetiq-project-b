"""
Tests for non-EDGAR fetchers.

All HTTP calls are mocked — no network access.
Tests verify:
  - Happy path: correct Signal schema + signal_type returned
  - Error path: HTTP failures return [] without crashing
  - Missing credentials: returns [] without crashing
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import date

import pytest

from schema.enums import CompanyType, DataSource, SignalType
from schema.models import Company, Signal


# ── AdzunaFetcher ─────────────────────────────────────────────────────────────

class TestAdzunaFetcher:

    def test_no_credentials_returns_empty(self, salesforce):
        from fetchers.adzuna import AdzunaFetcher
        with patch("fetchers.adzuna.settings") as mock_settings:
            mock_settings.ADZUNA_APP_ID = ""
            mock_settings.ADZUNA_APP_KEY = ""
            signals = AdzunaFetcher().fetch(salesforce)
        assert signals == []

    @patch("fetchers.adzuna.settings")
    def test_happy_path_returns_volume_and_mix(self, mock_settings, salesforce):
        from fetchers.adzuna import AdzunaFetcher
        mock_settings.ADZUNA_APP_ID = "test-id"
        mock_settings.ADZUNA_APP_KEY = "test-key"

        fetcher = AdzunaFetcher()
        fetcher.get_json = MagicMock(return_value={
            "results": [
                {"title": "Software Engineer"},
                {"title": "ML Engineer"},
                {"title": "Account Executive"},
                {"title": "Data Scientist"},
                {"title": "Backend Engineer"},
            ]
        })

        signals = fetcher.fetch(salesforce)
        signal_types = {s.signal_type for s in signals}
        assert SignalType.hiring_volume in signal_types
        assert SignalType.hiring_mix in signal_types

    @patch("fetchers.adzuna.settings")
    def test_http_error_returns_empty(self, mock_settings, salesforce):
        from fetchers.adzuna import AdzunaFetcher
        mock_settings.ADZUNA_APP_ID = "test-id"
        mock_settings.ADZUNA_APP_KEY = "test-key"
        fetcher = AdzunaFetcher()
        fetcher.get_json = MagicMock(side_effect=Exception("HTTP 500"))
        assert fetcher.fetch(salesforce) == []

    @patch("fetchers.adzuna.settings")
    def test_hiring_mix_breakdown_values(self, mock_settings, salesforce):
        from fetchers.adzuna import AdzunaFetcher
        mock_settings.ADZUNA_APP_ID = "test-id"
        mock_settings.ADZUNA_APP_KEY = "test-key"

        fetcher = AdzunaFetcher()
        fetcher.get_json = MagicMock(return_value={
            "results": [
                {"title": "ML Engineer"},       # AI/ML
                {"title": "Software Engineer"},  # Engineering
                {"title": "Account Executive"},  # Sales
                {"title": "Product Manager"},    # None of the above
            ]
        })
        signals = fetcher.fetch(salesforce)
        mix_signal = next(s for s in signals if s.signal_type == SignalType.hiring_mix)
        assert mix_signal.value["total"] == 4
        assert mix_signal.value["ai_ml_count"] == 1
        assert mix_signal.value["engineering_count"] == 1
        assert mix_signal.value["sales_count"] == 1


# ── AppStoreFetcher ───────────────────────────────────────────────────────────

class TestAppStoreFetcher:

    def test_happy_path_returns_rating_signal(self, salesforce):
        from fetchers.appstore import AppStoreFetcher
        fetcher = AppStoreFetcher()
        fetcher.get_json = MagicMock(return_value={
            "results": [{
                "trackName": "Salesforce",
                "averageUserRating": 4.5,
                "userRatingCount": 12000,
                "primaryGenreName": "Business",
            }]
        })
        signals = fetcher.fetch(salesforce)
        signal_types = {s.signal_type for s in signals}
        assert SignalType.app_store_rating in signal_types

    def test_no_results_returns_empty(self, salesforce):
        from fetchers.appstore import AppStoreFetcher
        fetcher = AppStoreFetcher()
        fetcher.get_json = MagicMock(return_value={"results": []})
        assert fetcher.fetch(salesforce) == []

    def test_http_error_returns_empty(self, salesforce):
        from fetchers.appstore import AppStoreFetcher
        fetcher = AppStoreFetcher()
        fetcher.get_json = MagicMock(side_effect=Exception("timeout"))
        assert fetcher.fetch(salesforce) == []

    def test_rating_value_is_float(self, salesforce):
        from fetchers.appstore import AppStoreFetcher
        fetcher = AppStoreFetcher()
        fetcher.get_json = MagicMock(return_value={
            "results": [{"trackName": "Salesforce", "averageUserRating": 4.2, "userRatingCount": 500}]
        })
        signals = fetcher.fetch(salesforce)
        rating_signal = next((s for s in signals if s.signal_type == SignalType.app_store_rating), None)
        assert rating_signal is not None
        assert isinstance(rating_signal.value, float)


# ── GitHubFetcher ─────────────────────────────────────────────────────────────

class TestGitHubFetcher:

    def test_happy_path_returns_oss_and_velocity(self, salesforce):
        from fetchers.github import GitHubFetcher
        fetcher = GitHubFetcher()
        fetcher._get_json = MagicMock(side_effect=[
            # org endpoint
            {"public_repos": 150, "followers": 5000, "created_at": "2010-01-01T00:00:00Z"},
            # repos list
            [{"name": "salesforce-sdk"}, {"name": "lwc"}],
            # commits for repo 1
            [{"sha": "abc"}, {"sha": "def"}],
            # commits for repo 2
            [{"sha": "xyz"}],
        ])
        signals = fetcher.fetch(salesforce)
        signal_types = {s.signal_type for s in signals}
        assert SignalType.oss_activity in signal_types
        assert SignalType.github_commit_velocity in signal_types

    def test_org_not_found_returns_empty(self, salesforce):
        from fetchers.github import GitHubFetcher
        fetcher = GitHubFetcher()
        fetcher._get_json = MagicMock(side_effect=Exception("404 Not Found"))
        assert fetcher.fetch(salesforce) == []

    def test_commit_velocity_value_is_sum(self, salesforce):
        from fetchers.github import GitHubFetcher
        fetcher = GitHubFetcher()
        fetcher._get_json = MagicMock(side_effect=[
            {"public_repos": 10, "followers": 100, "created_at": "2015-01-01T00:00:00Z"},
            [{"name": "repo-a"}, {"name": "repo-b"}, {"name": "repo-c"}],
            [{"sha": "1"}, {"sha": "2"}],  # 2 commits in repo-a
            [{"sha": "3"}],                 # 1 commit in repo-b
            [{"sha": "4"}, {"sha": "5"}, {"sha": "6"}],  # 3 in repo-c
        ])
        signals = fetcher.fetch(salesforce)
        vel = next(s for s in signals if s.signal_type == SignalType.github_commit_velocity)
        assert vel.value == 6  # 2+1+3


# ── WaybackFetcher ────────────────────────────────────────────────────────────

class TestWaybackFetcher:

    def test_happy_path_returns_pricing_signal(self, salesforce):
        from fetchers.wayback import WaybackFetcher
        fetcher = WaybackFetcher()
        fetcher.get_json = MagicMock(return_value=[
            ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            ["salesforce.com/pricing", "20240101120000", "https://salesforce.com/pricing", "text/html", "200", "abc", "12345"],
            ["salesforce.com/pricing", "20241201120000", "https://salesforce.com/pricing", "text/html", "200", "xyz", "11000"],
        ])
        signals = fetcher.fetch(salesforce)
        signal_types = {s.signal_type for s in signals}
        assert SignalType.pricing_page_history in signal_types

    def test_http_error_returns_empty(self, salesforce):
        from fetchers.wayback import WaybackFetcher
        fetcher = WaybackFetcher()
        fetcher.get_json = MagicMock(side_effect=Exception("CDX timeout"))
        assert fetcher.fetch(salesforce) == []

    def test_no_snapshots_returns_empty(self, salesforce):
        from fetchers.wayback import WaybackFetcher
        fetcher = WaybackFetcher()
        # Only a header row, no data rows
        fetcher.get_json = MagicMock(return_value=[
            ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]
        ])
        assert fetcher.fetch(salesforce) == []


# ── GoogleTrendsFetcher ───────────────────────────────────────────────────────

class TestGoogleTrendsFetcher:
    # TrendReq is imported lazily inside fetch(), so patch the source module.

    def test_http_error_returns_empty(self, salesforce):
        """pytrends errors should be caught and return [] gracefully."""
        from fetchers.google_trends import GoogleTrendsFetcher
        with patch("pytrends.request.TrendReq") as mock_cls:
            mock_cls.return_value.build_payload.side_effect = Exception("429 rate limit")
            fetcher = GoogleTrendsFetcher()
            signals = fetcher.fetch(salesforce)
        assert signals == []

    def test_returns_list(self, salesforce):
        """Even an empty result should be a list, not None or exception."""
        import pandas as pd
        from fetchers.google_trends import GoogleTrendsFetcher
        with patch("pytrends.request.TrendReq") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.interest_over_time.return_value = pd.DataFrame()
            mock_instance.related_queries.return_value = {}
            fetcher = GoogleTrendsFetcher()
            result = fetcher.fetch(salesforce)
        assert isinstance(result, list)


# ── WappalyzerFetcher ─────────────────────────────────────────────────────────

class TestWappalyzerFetcher:
    # Patch only subprocess.run to preserve real exception classes on the module.

    def test_no_node_returns_empty(self, salesforce):
        """If Node/wappalyzer isn't installed, should return [] gracefully."""
        from fetchers.wappalyzer import WappalyzerFetcher
        with patch("fetchers.wappalyzer.subprocess.run", side_effect=FileNotFoundError("node not found")):
            signals = WappalyzerFetcher().fetch(salesforce)
        assert signals == []

    def test_subprocess_error_returns_empty(self, salesforce):
        from fetchers.wappalyzer import WappalyzerFetcher
        with patch("fetchers.wappalyzer.subprocess.run", side_effect=Exception("subprocess failed")):
            signals = WappalyzerFetcher().fetch(salesforce)
        assert signals == []


# ── Signal schema compliance ──────────────────────────────────────────────────

class TestSignalSchemaCompliance:
    """Verify all fetchers return properly constructed Signal objects."""

    def _validate_signals(self, signals: list):
        for sig in signals:
            assert isinstance(sig, Signal), f"Expected Signal, got {type(sig)}"
            assert sig.entity_id, "Signal must have entity_id"
            assert sig.signal_type in SignalType, "signal_type must be valid enum"
            assert sig.signal_name, "Signal must have signal_name"
            assert sig.source in DataSource, "source must be valid enum"
            assert sig.reliability_tier in (1, 2, 3), "reliability_tier must be 1, 2, or 3"

    @patch("fetchers.adzuna.settings")
    def test_adzuna_signals_schema_valid(self, mock_settings, salesforce):
        from fetchers.adzuna import AdzunaFetcher
        mock_settings.ADZUNA_APP_ID = "id"
        mock_settings.ADZUNA_APP_KEY = "key"
        fetcher = AdzunaFetcher()
        fetcher.get_json = MagicMock(return_value={
            "results": [{"title": "Engineer"}, {"title": "ML Engineer"}]
        })
        self._validate_signals(fetcher.fetch(salesforce))

    def test_appstore_signals_schema_valid(self, salesforce):
        from fetchers.appstore import AppStoreFetcher
        fetcher = AppStoreFetcher()
        fetcher.get_json = MagicMock(return_value={
            "results": [{"trackName": "App", "averageUserRating": 4.0, "userRatingCount": 100}]
        })
        self._validate_signals(fetcher.fetch(salesforce))

    def test_github_signals_schema_valid(self, salesforce):
        from fetchers.github import GitHubFetcher
        fetcher = GitHubFetcher()
        fetcher._get_json = MagicMock(side_effect=[
            {"public_repos": 10, "followers": 100, "created_at": "2015-01-01T00:00:00Z"},
            [{"name": "repo-a"}],
            [{"sha": "1"}],
        ])
        self._validate_signals(fetcher.fetch(salesforce))
