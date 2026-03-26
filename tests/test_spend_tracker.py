"""
Tests for spend/tracker.py

File I/O only — no network, no mocks needed.
Uses pytest's tmp_path fixture to isolate each test.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from spend.tracker import SpendTracker


def _tracker(tmp_path) -> SpendTracker:
    return SpendTracker(ledger_path=str(tmp_path / "ledger.json"))


# ── would_exceed ─────────────────────────────────────────────────────────────

def test_would_exceed_fresh_tracker(tmp_path):
    """Empty ledger: small cost should not exceed default $5 limit."""
    assert not _tracker(tmp_path).would_exceed(0.50)


def test_would_exceed_at_limit(tmp_path):
    """Adding to a nearly-full day should trigger the limit."""
    t = _tracker(tmp_path)
    t.record("run-1", 4.99)
    assert t.would_exceed(0.02)  # 4.99 + 0.02 = 5.01 > 5.00


def test_would_exceed_exact_limit(tmp_path):
    """Exactly at limit should not trigger (uses strict >)."""
    t = _tracker(tmp_path)
    t.record("run-1", 4.00)
    # 4.00 + 1.00 = 5.00, not > 5.00
    assert not t.would_exceed(1.00)


def test_would_exceed_zero_cost(tmp_path):
    """$0 cost should never exceed limit."""
    t = _tracker(tmp_path)
    t.record("run-1", 4.99)
    assert not t.would_exceed(0.0)


# ── record + daily_total ─────────────────────────────────────────────────────

def test_record_persists_across_instances(tmp_path):
    """Cost recorded by one tracker instance is visible to a fresh instance."""
    path = str(tmp_path / "ledger.json")
    SpendTracker(ledger_path=path).record("run-1", 0.042)
    assert SpendTracker(ledger_path=path).daily_total() == pytest.approx(0.042)


def test_record_accumulates(tmp_path):
    t = _tracker(tmp_path)
    t.record("run-1", 0.10)
    t.record("run-2", 0.05)
    assert t.daily_total() == pytest.approx(0.15)


def test_record_with_note(tmp_path):
    path = str(tmp_path / "ledger.json")
    SpendTracker(ledger_path=path).record("run-1", 0.01, note="smoke test")
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger[0]["note"] == "smoke test"


def test_record_without_note_omits_key(tmp_path):
    path = str(tmp_path / "ledger.json")
    SpendTracker(ledger_path=path).record("run-1", 0.01)
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert "note" not in ledger[0]


def test_record_contains_expected_fields(tmp_path):
    path = str(tmp_path / "ledger.json")
    SpendTracker(ledger_path=path).record("run-abc", 0.05)
    entry = json.loads((tmp_path / "ledger.json").read_text())[0]
    assert "ts" in entry
    assert "date" in entry
    assert entry["analysis_id"] == "run-abc"
    assert entry["cost_usd"] == pytest.approx(0.05)
    assert "model" in entry


# ── status ───────────────────────────────────────────────────────────────────

def test_status_structure(tmp_path):
    status = _tracker(tmp_path).status()
    assert "date" in status
    assert "spent_usd" in status
    assert "limit_usd" in status
    assert "remaining_usd" in status
    assert "analyses_today" in status
    assert "pct_used" in status


def test_status_empty_ledger(tmp_path):
    status = _tracker(tmp_path).status()
    assert status["spent_usd"] == 0.0
    assert status["analyses_today"] == 0
    assert status["pct_used"] == 0.0


def test_status_after_record(tmp_path):
    t = _tracker(tmp_path)
    t.record("run-1", 2.50)
    status = t.status()
    assert status["spent_usd"] == pytest.approx(2.50)
    assert status["analyses_today"] == 1
    assert status["remaining_usd"] == pytest.approx(2.50)
    assert status["pct_used"] == pytest.approx(50.0)


def test_remaining_never_below_zero(tmp_path):
    t = _tracker(tmp_path)
    t.record("run-1", 10.00)  # exceeds $5 limit
    status = t.status()
    assert status["remaining_usd"] == 0.0


# ── resilience ───────────────────────────────────────────────────────────────

def test_corrupt_ledger_returns_zero(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("not valid json {{")
    t = SpendTracker(ledger_path=str(path))
    assert t.daily_total() == 0.0
    assert not t.would_exceed(1.0)


def test_missing_ledger_file_is_fine(tmp_path):
    """Tracker with a non-existent path should start clean."""
    t = SpendTracker(ledger_path=str(tmp_path / "nonexistent.json"))
    assert t.daily_total() == 0.0


def test_record_creates_parent_dirs(tmp_path):
    nested_path = str(tmp_path / "deep" / "nested" / "ledger.json")
    t = SpendTracker(ledger_path=nested_path)
    t.record("run-1", 0.01)
    assert (tmp_path / "deep" / "nested" / "ledger.json").exists()


# ── monthly_total ─────────────────────────────────────────────────────────────

def test_monthly_total_sums_current_month(tmp_path):
    t = _tracker(tmp_path)
    t.record("run-1", 1.00)
    t.record("run-2", 2.00)
    assert t.monthly_total() == pytest.approx(3.00)


def test_monthly_total_excludes_other_months(tmp_path):
    """Manually inject a past-month entry and verify it's excluded from current month."""
    path = tmp_path / "ledger.json"
    entry = {
        "ts": "2025-01-15T12:00:00+00:00",
        "date": "2025-01-15",
        "analysis_id": "old-run",
        "cost_usd": 99.00,
        "model": "test",
    }
    path.write_text(json.dumps([entry]))
    t = SpendTracker(ledger_path=str(path))
    # Current month should not include the January 2025 entry
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if current_month != "2025-01":
        assert t.monthly_total() == 0.0
