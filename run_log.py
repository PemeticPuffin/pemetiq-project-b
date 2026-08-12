"""Durable per-run analytics log (Supabase).

One row per completed live run — which app, which tool, which company, cost —
written to a Supabase table shared by Cadillaq and Manseil. This is the durable
record of what visitors actually do; it is separate from the spend ledger, which
is only an ephemeral daily safety valve.

Design rules:
  * Fails OPEN and SILENT. Any error here — network, config, bad data — must
    never affect a visitor's run. Analytics is never worth a broken app.
  * No-op when unconfigured. If SUPABASE_URL / SUPABASE_KEY are unset (local
    dev, tests), logging quietly does nothing.
  * Non-blocking. The insert runs on a daemon thread so it never adds latency
    to the response the visitor is waiting on.
  * Stdlib only (urllib) — no new dependency to deploy.

Supabase setup (run once in the SQL editor):

    create table if not exists run_log (
      id       bigint generated always as identity primary key,
      ts       timestamptz not null default now(),
      app      text not null,          -- 'cadillaq' | 'manseil'
      tool     text,                   -- which tool/mode the visitor ran
      company  text,                   -- subject company
      cost_usd numeric(10,6),          -- run cost if known
      meta     jsonb                   -- app-specific extras
    );
    create index if not exists run_log_ts_idx  on run_log (ts desc);
    create index if not exists run_log_app_idx on run_log (app);

Then set SUPABASE_URL (e.g. https://xxxx.supabase.co) and SUPABASE_KEY
(service_role key — server-side only, never shipped to the browser) as env
vars locally and on Railway.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request

logger = logging.getLogger(__name__)

_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_KEY = os.getenv("SUPABASE_KEY", "")
_TABLE = os.getenv("RUN_LOG_TABLE", "run_log")
_TIMEOUT = 4  # seconds; a slow analytics write must never hang a run


def _enabled() -> bool:
    return bool(_URL and _KEY)


def _post(row: dict) -> None:
    """Insert one row via the Supabase REST API. Swallows every error."""
    try:
        body = json.dumps(row).encode("utf-8")
        req = urllib.request.Request(
            f"{_URL}/rest/v1/{_TABLE}",
            data=body,
            method="POST",
            headers={
                "apikey": _KEY,
                "Authorization": f"Bearer {_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT).close()
    except Exception:  # noqa: BLE001 — analytics must never surface an error
        logger.debug("run_log insert failed", exc_info=True)


def log_run(
    *,
    app: str,
    tool: str | None = None,
    company: str | None = None,
    cost_usd: float | None = None,
    meta: dict | None = None,
) -> None:
    """Record one completed run. Fire-and-forget; returns immediately.

    Args:
        app:      'cadillaq' or 'manseil'.
        tool:     Which tool/mode the visitor ran.
        company:  Subject company name.
        cost_usd: Run cost in USD, when known.
        meta:     Optional app-specific extras (JSON-serialisable).
    """
    if not _enabled():
        return
    row: dict = {"app": app}
    if tool is not None:
        row["tool"] = tool
    if company is not None:
        row["company"] = company
    if cost_usd is not None:
        row["cost_usd"] = round(float(cost_usd), 6)
    if meta:
        row["meta"] = meta
    threading.Thread(target=_post, args=(row,), daemon=True).start()
