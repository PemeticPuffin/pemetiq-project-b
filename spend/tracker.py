"""
SpendTracker — daily API cost ledger.

Two-layer cost control:
  1. This class: in-app daily counter, pre-run check, post-run record
  2. Anthropic Console: monthly hard cap (set to $50 as backstop)

Ledger format (data/spend_ledger.json):
  [
    {
      "ts": "2026-03-20T14:32:01",
      "date": "2026-03-20",
      "analysis_id": "abc-123",
      "cost_usd": 0.042,
      "model": "claude-sonnet-4-6",
      "note": "optional"
    },
    ...
  ]
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from config import settings


class SpendTracker:

    def __init__(self, ledger_path: str | None = None):
        self._path = Path(ledger_path or settings.SPEND_LEDGER_PATH)
        self._limit = settings.DAILY_SPEND_LIMIT_USD
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def would_exceed(self, estimated_cost: float) -> bool:
        """Return True if adding estimated_cost would exceed today's limit."""
        return (self.daily_total() + estimated_cost) > self._limit

    def record(
        self,
        analysis_id: str,
        cost_usd: float,
        note: str = "",
    ) -> None:
        """Append a cost entry to the ledger after a completed run."""
        now = datetime.now(timezone.utc)
        entry = {
            "ts": now.isoformat(timespec="seconds"),
            "date": now.date().isoformat(),
            "analysis_id": analysis_id,
            "cost_usd": round(cost_usd, 6),
            "model": settings.ANTHROPIC_MODEL,
        }
        if note:
            entry["note"] = note

        ledger = self._load()
        ledger.append(entry)
        self._save(ledger)

    def status(self) -> dict:
        """Return today's spend summary for the UI sidebar."""
        today = datetime.now(timezone.utc).date().isoformat()
        ledger = self._load()
        today_entries = [e for e in ledger if e.get("date") == today]
        spent = round(sum(e.get("cost_usd", 0) for e in today_entries), 4)
        return {
            "date": today,
            "spent_usd": spent,
            "limit_usd": self._limit,
            "remaining_usd": round(max(0.0, self._limit - spent), 4),
            "analyses_today": len(today_entries),
            "pct_used": round(min(spent / self._limit * 100, 100), 1) if self._limit else 0,
        }

    def daily_total(self, date_str: str | None = None) -> float:
        """Sum of costs for a given date (defaults to today)."""
        target = date_str or datetime.now(timezone.utc).date().isoformat()
        ledger = self._load()
        return round(sum(e.get("cost_usd", 0) for e in ledger if e.get("date") == target), 6)

    def monthly_total(self, year_month: str | None = None) -> float:
        """Sum of costs for a given YYYY-MM (defaults to current month)."""
        target = year_month or datetime.now(timezone.utc).strftime("%Y-%m")
        ledger = self._load()
        return round(
            sum(e.get("cost_usd", 0) for e in ledger if e.get("date", "").startswith(target)),
            4,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, ledger: list[dict]) -> None:
        self._path.write_text(json.dumps(ledger, indent=2))
