"""
EDGAR fetcher — three signal types:
  1. XBRL structured financials (revenue, gross margin, operating income, EPS)
  2. Filing submissions metadata (filing history, latency as a growth proxy)
  3. 8-K full-text search (earnings call content, language change detection)
"""
from __future__ import annotations

import re
from datetime import date, datetime

from fetchers.base import BaseFetcher
from schema.enums import DataSource, SignalType
from schema.models import Company, Signal

_BASE = "https://data.sec.gov"
_SEARCH = "https://efts.sec.gov/LATEST/search-index"

# XBRL concepts to fetch, in priority order per metric
_REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueServicesNet",
]
_GROSS_PROFIT_CONCEPTS = ["GrossProfit"]
_OPERATING_INCOME_CONCEPTS = ["OperatingIncomeLoss"]
_EPS_CONCEPTS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]


class EdgarFetcher(BaseFetcher):

    def fetch(self, company: Company) -> list[Signal]:
        if not company.cik:
            return []

        signals: list[Signal] = []
        cik_padded = company.cik.zfill(10)

        signals.extend(self._fetch_financials(company, cik_padded))
        signals.extend(self._fetch_filing_language(company, cik_padded))

        return signals

    # ------------------------------------------------------------------
    # XBRL financials
    # ------------------------------------------------------------------

    def _fetch_financials(self, company: Company, cik_padded: str) -> list[Signal]:
        url = f"{_BASE}/api/xbrl/companyfacts/CIK{cik_padded}.json"
        try:
            data = self.get_json(url)
        except Exception:
            return []

        us_gaap = data.get("facts", {}).get("us-gaap", {})
        signals: list[Signal] = []
        source_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={company.cik}"

        # Step 1: find the most recent fiscal year-end across all revenue concepts.
        # This anchors all subsequent lookups to the same period — prevents
        # mismatched periods (e.g. FY2017 revenue vs FY2025 gross profit).
        anchor_end = self._find_most_recent_annual_end(us_gaap, _REVENUE_CONCEPTS)

        # Revenue — anchored to most recent fiscal year
        rev_signal = self._extract_annual_concept(
            company, us_gaap, _REVENUE_CONCEPTS,
            SignalType.annual_revenue, "annual_revenue_usd", "USD",
            anchor_end=anchor_end,
        )
        if rev_signal:
            signals.append(rev_signal)

            # Revenue growth — prior year entry for YoY calculation
            prior_end = self._find_prior_annual_end(us_gaap, _REVENUE_CONCEPTS, anchor_end)
            if prior_end:
                prior_signal = self._extract_annual_concept(
                    company, us_gaap, _REVENUE_CONCEPTS,
                    SignalType.annual_revenue, "annual_revenue_usd", "USD",
                    anchor_end=prior_end,
                )
                if prior_signal and isinstance(prior_signal.value, (int, float)) and prior_signal.value:
                    growth = round(
                        (rev_signal.value - prior_signal.value) / prior_signal.value * 100, 2
                    )
                    signals.append(Signal(
                        entity_id=company.entity_id,
                        signal_type=SignalType.revenue_growth,
                        signal_name="revenue_growth_yoy_pct",
                        value=growth,
                        unit="pct",
                        period_start=prior_signal.period_end,
                        period_end=rev_signal.period_end,
                        source=DataSource.edgar_xbrl,
                        source_url=source_url,
                        reliability_tier=1,
                        raw={"current": rev_signal.value, "prior": prior_signal.value},
                    ))

        # Gross margin — anchored to same fiscal year end
        gp_signal = self._extract_annual_concept(
            company, us_gaap, _GROSS_PROFIT_CONCEPTS,
            SignalType.gross_margin, "gross_profit_usd", "USD",
            anchor_end=anchor_end,
        )
        if gp_signal and rev_signal and isinstance(rev_signal.value, (int, float)) and rev_signal.value:
            gp = gp_signal.value
            rev = rev_signal.value
            if isinstance(gp, (int, float)) and rev:
                signals.append(Signal(
                    entity_id=company.entity_id,
                    signal_type=SignalType.gross_margin,
                    signal_name="gross_margin_pct",
                    value=round((gp / rev) * 100, 2),
                    unit="pct",
                    period_end=rev_signal.period_end,
                    source=DataSource.edgar_xbrl,
                    source_url=source_url,
                    reliability_tier=1,
                ))

        # Operating income — anchored
        oi_signal = self._extract_annual_concept(
            company, us_gaap, _OPERATING_INCOME_CONCEPTS,
            SignalType.operating_income, "operating_income_usd", "USD",
            anchor_end=anchor_end,
        )
        if oi_signal:
            signals.append(oi_signal)

        # EPS — anchored
        eps_signal = self._extract_annual_concept(
            company, us_gaap, _EPS_CONCEPTS,
            SignalType.eps, "eps_diluted_usd", "USD/shares",
            anchor_end=anchor_end,
        )
        if eps_signal:
            signals.append(eps_signal)

        return signals

    def _extract_annual_concept(
        self,
        company: Company,
        us_gaap: dict,
        concepts: list[str],
        signal_type: SignalType,
        signal_name: str,
        unit: str,
        anchor_end: str | None = None,
    ) -> Signal | None:
        for concept in concepts:
            node = us_gaap.get(concept)
            if not node:
                continue
            units_data = node.get("units", {})
            values = units_data.get("USD", units_data.get("USD/shares", []))
            annual = [
                v for v in values
                if v.get("form") == "10-K" and _is_annual_period(v.get("start"), v.get("end"))
            ]
            if not annual:
                continue
            if anchor_end:
                anchor_date = _parse_date(anchor_end)
                anchored = [
                    v for v in annual
                    if anchor_date and _parse_date(v.get("end"))
                    and abs((_parse_date(v.get("end")) - anchor_date).days) <= 60
                ] if anchor_date else []
                if not anchored:
                    # This concept has no data near the anchor year — try next concept
                    continue
                candidates = anchored
            else:
                candidates = annual
            candidates.sort(key=lambda x: x.get("end", ""), reverse=True)
            latest = candidates[0]
            return Signal(
                entity_id=company.entity_id,
                signal_type=signal_type,
                signal_name=signal_name,
                value=latest.get("val"),
                unit=unit,
                period_start=_parse_date(latest.get("start")),
                period_end=_parse_date(latest.get("end")),
                source=DataSource.edgar_xbrl,
                source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={company.cik}",
                reliability_tier=1,
                raw={"concept": concept, "entry": latest},
            )
        return None

    def _find_most_recent_annual_end(self, us_gaap: dict, concepts: list[str]) -> str | None:
        """Find the most recent fiscal year-end date across all candidate concepts."""
        latest = None
        for concept in concepts:
            node = us_gaap.get(concept)
            if not node:
                continue
            values = node.get("units", {}).get("USD", [])
            for v in values:
                if v.get("form") == "10-K" and _is_annual_period(v.get("start"), v.get("end")):
                    end = v.get("end", "")
                    if end and (latest is None or end > latest):
                        latest = end
        return latest

    def _find_prior_annual_end(
        self, us_gaap: dict, concepts: list[str], current_end: str | None
    ) -> str | None:
        """Find the fiscal year-end one year before current_end."""
        if not current_end:
            return None
        current_date = _parse_date(current_end)
        if not current_date:
            return None
        best = None
        for concept in concepts:
            node = us_gaap.get(concept)
            if not node:
                continue
            values = node.get("units", {}).get("USD", [])
            for v in values:
                if not (v.get("form") == "10-K" and _is_annual_period(v.get("start"), v.get("end"))):
                    continue
                end_date = _parse_date(v.get("end"))
                if not end_date:
                    continue
                diff = (current_date - end_date).days
                if 300 <= diff <= 430:
                    end_str = v.get("end", "")
                    if best is None or end_str > best:
                        best = end_str
        return best

    # ------------------------------------------------------------------
    # 8-K language change detection
    # ------------------------------------------------------------------

    def _fetch_filing_language(self, company: Company, cik_padded: str) -> list[Signal]:
        """Pull recent 8-K filings and flag metric definition changes."""
        url = f"{_BASE}/submissions/CIK{cik_padded}.json"
        try:
            data = self.get_json(url)
        except Exception:
            return []

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])

        # Count 8-Ks in the last 12 months as a proxy for IR activity
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        recent_8k = [
            d for f, d in zip(forms, dates)
            if f == "8-K" and d >= cutoff
        ]

        if not recent_8k:
            return []

        return [Signal(
            entity_id=company.entity_id,
            signal_type=SignalType.filing_language_change,
            signal_name="8k_count_12mo",
            value=len(recent_8k),
            unit="count",
            source=DataSource.edgar_filings,
            source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={company.cik}&type=8-K",
            reliability_tier=1,
            raw={"recent_8k_dates": recent_8k[:10]},
        )]


def fetch_recent_filing_text(cik: str, max_chars: int = 20_000) -> tuple[str, str, str, str] | None:
    """
    Fetch narrative MD&A text from the most recent 10-Q or 10-K.

    Only returns 10-Q or 10-K — never falls back to 8-K, which is too short
    and too inconsistent to be a reliable source for claim extraction.
    Returns (text, source_url, form_type, filing_date) or None if unavailable.
    Strips HTML; extracts MD&A section; truncates to max_chars.
    """
    import html as _html
    import re as _re
    import requests as _req

    cik_padded = cik.zfill(10)
    cik_int = str(int(cik))
    headers = {"User-Agent": "Pemetiq/ProjectB contact@pemetiq.com"}

    # 1. Load submissions index
    try:
        subs = _req.get(
            f"{_BASE}/submissions/CIK{cik_padded}.json",
            headers=headers, timeout=15,
        ).json()
    except Exception:
        return None

    filings = subs.get("filings", {}).get("recent", {})
    forms        = filings.get("form", [])
    accessions   = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [""] * len(forms))
    filing_dates = filings.get("filingDate", [""] * len(forms))

    # 2. Find the most recent 10-Q or 10-K — no 8-K fallback.
    # 8-K filings are too short and inconsistent for claim extraction.
    candidates = list(zip(forms, accessions, primary_docs, filing_dates))

    accession, primary_doc, form_type, filing_date = None, None, None, ""
    for target in ["10-Q", "10-K"]:
        for form, acc, primary, fdate in candidates:
            if form == target:
                accession, primary_doc, form_type, filing_date = acc, primary, target, fdate
                break
        if accession:
            break

    if not accession:
        return None

    # 3. Find the best document in the filing directory
    acc_nodash = accession.replace("-", "")
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}"

    try:
        dir_items = _req.get(
            f"{base_url}/index.json", headers=headers, timeout=15
        ).json().get("directory", {}).get("item", [])
        filenames = [item["name"] for item in dir_items]
    except Exception:
        filenames = []

    doc_filename = _pick_document(form_type, primary_doc, filenames)
    if not doc_filename:
        return None

    # 4. Fetch, strip HTML, truncate
    try:
        resp = _req.get(f"{base_url}/{doc_filename}", headers=headers, timeout=25)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return None

    text = _re.sub(r"<[^>]+>", " ", html)
    text = _html.unescape(text)
    text = _re.sub(r"\s+", " ", text).strip()

    # For 10-Q/10-K: skip XBRL header and land in the MD&A narrative section
    if form_type in ("10-Q", "10-K"):
        text = _extract_mda_section(text, max_chars)
    else:
        if len(text) > max_chars:
            text = text[:max_chars] + "…"

    # Require at least 1,000 chars — anything less isn't a usable MD&A section
    if not text or len(text) < 1_000:
        return None

    source_url = f"{base_url}/{accession}-index.html"
    return text, source_url, form_type, filing_date


def _extract_mda_section(text: str, max_chars: int) -> str:
    """
    Find and return the MD&A section from a 10-Q/10-K.

    The MD&A marker appears twice: once in the table of contents, once as the
    actual section header. We want the section header — i.e., the occurrence
    that is followed by substantial narrative text, not a page number.
    Strategy: collect all occurrences of known markers, skip any that are
    within 5,000 chars of the previous one (TOC entries are close together),
    and take the first isolated occurrence.
    """
    markers = [
        "Management's Discussion and Analysis",
        "MANAGEMENT'S DISCUSSION AND ANALYSIS",
        "MANAGEMENT&#8217;S DISCUSSION",
        "Management&#8217;s Discussion",
        "ITEM 2. MANAGEMENT",
        "Item 2. Management",
    ]

    # Collect all hit positions across all markers
    hits = []
    for marker in markers:
        pos = 0
        while True:
            idx = text.find(marker, pos)
            if idx == -1:
                break
            hits.append(idx)
            pos = idx + len(marker)

    hits.sort()

    # The MD&A marker appears at least twice: once in the TOC, once as the
    # actual section header. The actual section is always the LAST occurrence.
    # Exception: if there's only one hit, use it.
    if hits:
        start = hits[-1]
    else:
        # No marker found — skip first 25% of doc (past XBRL header)
        start = len(text) // 4

    excerpt = text[start:start + max_chars]
    if start + max_chars < len(text):
        excerpt += "…"
    return excerpt


def _pick_document(form_type: str, primary_doc: str, filenames: list[str]) -> str | None:
    """Select the best document from a filing's file list."""
    def is_htm(fn): return fn.lower().endswith((".htm", ".html"))
    def is_support(fn):
        low = fn.lower()
        return any(x in low for x in ("index", "_htm.xml", ".xsd", ".xml", "r1.", "r2.",
                                       "ex3", "ex4", "ex31", "ex32", "show.js", "report.css"))

    if form_type in ("10-Q", "10-K"):
        # Prefer ticker-named htm (e.g. crm-20251031.htm) — the full inline XBRL filing
        # These are large files that contain both structured data and readable narrative
        if primary_doc and is_htm(primary_doc) and primary_doc in filenames:
            return primary_doc
        # Otherwise find largest htm file that isn't a support file
        htm_files = [fn for fn in filenames if is_htm(fn) and not is_support(fn)]
        # Sort by name length descending (ticker-named files tend to be longest)
        htm_files.sort(key=len, reverse=True)
        return htm_files[0] if htm_files else None

    if form_type == "8-K":
        for fn in filenames:
            if "ex991" in fn.lower() and is_htm(fn):
                return fn
        for fn in filenames:
            if is_htm(fn) and not is_support(fn):
                return fn
        return None

    return None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_annual_period(start: str | None, end: str | None) -> bool:
    """Return True if start→end spans at least 300 days (annual, not quarterly)."""
    s = _parse_date(start)
    e = _parse_date(end)
    if not s or not e:
        return False
    return (e - s).days >= 300
