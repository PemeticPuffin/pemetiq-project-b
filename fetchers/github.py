"""
GitHub API fetcher.
Returns:
  - oss_activity: public repo count, total stars
  - github_commit_velocity: recent commit activity on top repos
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from config import settings
from fetchers.base import BaseFetcher
from schema.enums import DataSource, SignalType
from schema.models import Company, Signal

_BASE = "https://api.github.com"
_TOP_REPOS = 3  # inspect commit history on top N repos by stars


class GitHubFetcher(BaseFetcher):

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "User-Agent": "Pemetiq/ProjectB"}
        if settings.GITHUB_TOKEN:
            h["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
        return h

    def _get_json(self, url: str, params: dict | None = None) -> dict | list:
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch(self, company: Company) -> list[Signal]:
        # Derive likely GitHub org name from domain (e.g. salesforce.com → salesforce)
        org = company.domain.split(".")[0]
        signals: list[Signal] = []

        org_signal = self._fetch_org(company, org)
        if org_signal:
            signals.append(org_signal)

        commit_signal = self._fetch_commit_velocity(company, org)
        if commit_signal:
            signals.append(commit_signal)

        return signals

    def _fetch_org(self, company: Company, org: str) -> Signal | None:
        try:
            data = self._get_json(f"{_BASE}/orgs/{org}")
        except Exception:
            return None

        return Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.oss_activity,
            signal_name="github_public_repos",
            value=data.get("public_repos", 0),
            unit="count",
            source=DataSource.github_api,
            source_url=f"https://github.com/{org}",
            reliability_tier=2,
            raw={
                "followers": data.get("followers"),
                "created_at": data.get("created_at"),
                "org": org,
            },
        )

    def _fetch_commit_velocity(self, company: Company, org: str) -> Signal | None:
        try:
            repos = self._get_json(
                f"{_BASE}/orgs/{org}/repos",
                params={"sort": "pushed", "direction": "desc", "per_page": _TOP_REPOS},
            )
        except Exception:
            return None

        if not isinstance(repos, list) or not repos:
            return None

        cutoff = (date.today() - timedelta(days=90)).isoformat()
        recent_commits = 0
        repos_checked = 0

        for repo in repos[:_TOP_REPOS]:
            repo_name = repo.get("name")
            if not repo_name:
                continue
            try:
                commits = self._get_json(
                    f"{_BASE}/repos/{org}/{repo_name}/commits",
                    params={"since": f"{cutoff}T00:00:00Z", "per_page": 100},
                )
                if isinstance(commits, list):
                    recent_commits += len(commits)
                    repos_checked += 1
            except Exception:
                continue

        if repos_checked == 0:
            return None

        return Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.github_commit_velocity,
            signal_name="commits_90d_top_repos",
            value=recent_commits,
            unit="count",
            period_start=date.today() - timedelta(days=90),
            period_end=date.today(),
            source=DataSource.github_api,
            source_url=f"https://github.com/{org}",
            reliability_tier=2,
            raw={"repos_checked": repos_checked, "org": org},
        )
