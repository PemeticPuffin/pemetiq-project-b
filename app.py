"""
Pemetiq Manseil — Streamlit UI
Run: streamlit run app.py
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import anthropic
import streamlit as st
from PIL import Image

_ASSETS = Path(__file__).parent / "assets"

st.set_page_config(
    page_title="Manseil | Pemetiq",
    page_icon=Image.open(_ASSETS / "favicon.png"),
    layout="centered",
    initial_sidebar_state="collapsed",
)

def _b64_img(path: Path) -> str:
    """Return a base64 data URI for embedding an image in HTML."""
    data = base64.b64encode(path.read_bytes()).decode()
    suffix = path.suffix.lstrip(".")
    mime = "png" if suffix == "png" else "jpeg"
    return f"data:image/{mime};base64,{data}"

from schema.enums import CompanyType, DataSource, InputType
from schema.models import Company
from pipeline.orchestrator import AnalysisResult, run_analysis
from utils.company_lookup import lookup_cik

NAVY  = "#001731"
TEAL  = "#1A5C6A"
CORAL = "#E8643B"

SIGNAL_SOURCES = [
    "SEC EDGAR", "Google Trends", "GitHub", "App Store",
    "Job postings", "Wayback Machine", "GDELT", "Wappalyzer",
]

# Human-readable labels for signal names shown in Signal Breakdown
_SIGNAL_NAME_DISPLAY: dict[str, str] = {
    # EDGAR — financials
    "annual_revenue":              "Annual revenue (EDGAR)",
    "revenue_growth":              "Revenue growth YoY (EDGAR)",
    "gross_margin":                "Gross margin (EDGAR)",
    "operating_income":            "Operating income (EDGAR)",
    "eps":                         "Earnings per share (EDGAR)",
    "8k_count_12mo":               "8-K filings last 12 months (EDGAR)",
    "filing_language_change":      "Filing language changes (EDGAR)",
    # Google Trends
    "search_interest_52wk_avg":    "52-week search interest (Google Trends)",
    "search_trend_5yr":            "5-year search trend (Google Trends)",
    "search_share_vs_competitors": "Search share vs. competitors (Google Trends)",
    # GitHub
    "github_commit_velocity":      "Open-source commit activity (GitHub)",
    "github_oss_activity":         "Open-source repo presence (GitHub)",
    "oss_repos_count":             "Public repositories (GitHub)",
    # App Store
    "appstore_rating_top_app":     "Top app rating (App Store)",
    # Job postings
    "adzuna_job_count":            "Open job postings (Adzuna)",
    "adzuna_hiring_mix":           "Hiring function breakdown (Adzuna)",
    # Wayback Machine
    "wayback_pricing_snapshots":   "Pricing page history (Wayback Machine)",
    # GDELT
    "gdelt_news_volume":           "News coverage volume (GDELT)",
    "gdelt_news_tone":             "News sentiment (GDELT)",
    # Wappalyzer
    "wappalyzer_tech_stack":       "Technology stack (Wappalyzer)",
}

def _signal_display_name(signal_name: str) -> str:
    """Return a human-readable label for a signal name, falling back to title-casing the slug."""
    if signal_name in _SIGNAL_NAME_DISPLAY:
        return _SIGNAL_NAME_DISPLAY[signal_name]
    # Generic fallback: strip prefixes and title-case
    name = signal_name.replace("appstore_app_", "App: ").replace("_", " ")
    return name.title()

# Maps DataSource enum values → display label for source-coverage disclosure
_SOURCE_DISPLAY: dict[str, str] = {
    DataSource.edgar_xbrl:    "SEC EDGAR",
    DataSource.edgar_filings: "SEC EDGAR",
    DataSource.google_trends: "Google Trends",
    DataSource.github_api:    "GitHub",
    DataSource.apple_appstore:"App Store",
    DataSource.adzuna:        "Job postings",
    DataSource.wayback_cdx:   "Wayback Machine",
    DataSource.gdelt:         "GDELT",
    DataSource.wappalyzer:    "Wappalyzer",
}

VERDICT_STYLES: dict[str, tuple[str, str]] = {
    "supported":             ("#1a7a4a", "Supported"),
    "partially_supported":   (TEAL,      "Partially Supported"),
    "contested":             (CORAL,     "Contested"),
    "insufficient_evidence": ("#666",    "Insufficient Evidence"),
    "not_testable":          ("#999",    "Not Testable"),
}
STRENGTH_LABELS = {"strong": "●●●", "moderate": "●●○", "weak": "●○○"}

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&display=swap');

/* ── Base ── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="block-container"] {
    font-family: 'DM Sans', sans-serif !important;
    background: #f8f9fb !important;
    color: #001731 !important;
}

/* ── Hide Streamlit chrome ── */
header[data-testid="stHeader"], #MainMenu, footer,
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] { display: none !important; }

/* ── Layout spacing ── */
[data-testid="block-container"] {
    padding-top: 0 !important;
    padding-bottom: 4rem !important;
}
[data-testid="stVerticalBlock"] { gap: 1.1rem !important; }
[data-testid="column"] [data-testid="stVerticalBlock"] { gap: 0.4rem !important; }

/* ── Input labels ── */
[data-testid="stTextInput"] label,
[data-testid="stTextArea"]  label,
[data-testid="stRadio"] > label {
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: #001731 !important;
}

/* ── Text inputs ── */
[data-testid="stTextInput"] input {
    border: 2px solid #e2e4e8 !important;
    border-radius: 0.5rem !important;
    padding: 0.75rem 1rem !important;
    font-size: 0.9rem !important;
    color: #001731 !important;
    background: #ffffff !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-testid="stTextInput"] input:hover  { border-color: #c4c6cf !important; }
[data-testid="stTextInput"] input:focus  {
    border-color: #001731 !important;
    box-shadow: 0 0 0 2px rgba(0,23,49,0.08) !important;
}
[data-testid="stTextInput"] input::placeholder { color: #9aa3ac !important; }

/* ── Text area ── */
[data-testid="stTextArea"] textarea {
    border: 2px solid #e2e4e8 !important;
    border-radius: 0.5rem !important;
    font-size: 0.9rem !important;
    transition: border-color 0.18s !important;
}
[data-testid="stTextArea"] textarea:focus {
    border-color: #001731 !important;
    box-shadow: 0 0 0 2px rgba(0,23,49,0.08) !important;
}
[data-testid="stTextArea"] textarea::placeholder { color: #9aa3ac !important; }

/* ══════════════════════════════════════════════════════
   SEGMENTED CONTROL — card button style
   st.segmented_control renders real <button> elements so
   centering and sizing work without CSS hacks.
══════════════════════════════════════════════════════ */
[data-testid="stSegmentedControl"] {
    width: 100% !important;
}
/* Strip the default pill-container chrome */
[data-testid="stSegmentedControl"] > div {
    display: flex !important;
    gap: 0.75rem !important;
    background: none !important;
    border: none !important;
    padding: 0 !important;
    border-radius: 0 !important;
    width: 100% !important;
    box-shadow: none !important;
}
/* Each option as an individual card */
[data-testid="stSegmentedControl"] button {
    flex: 1 1 0 !important;
    border: 2px solid #e2e4e8 !important;
    border-radius: 0.5rem !important;
    padding: 0.85rem 0.75rem !important;
    background: #ffffff !important;
    color: #74777f !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    text-align: center !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
    box-shadow: none !important;
}
[data-testid="stSegmentedControl"] button:hover {
    border-color: #c4c6cf !important;
    background: #f2f4f6 !important;
    color: #74777f !important;
}
/* Selected state — works across Streamlit versions */
[data-testid="stSegmentedControl"] button[aria-selected="true"],
[data-testid="stSegmentedControl"] button[data-selected="true"],
[data-testid="stSegmentedControl"] button.selected {
    border-color: #001731 !important;
    background: #ffffff !important;
    color: #001731 !important;
}

/* Company type — compact, auto-width pills */
[data-testid="column"] [data-testid="stSegmentedControl"] > div {
    gap: 0.5rem !important;
}
[data-testid="column"] [data-testid="stSegmentedControl"] button {
    flex: none !important;
    padding: 0.5rem 0.9rem !important;
    font-size: 0.88rem !important;
}

/* ══════════════════════════════════════════════════════
   BUTTONS
   Ghost: all secondary buttons — transparent + ghost border.
   Run (primary): Coral #E8643B per design spec.
══════════════════════════════════════════════════════ */

/* Ghost style for all st.button() calls */
#root [data-testid="stButton"] button {
    background: transparent !important;
    color: #001731 !important;
    border: 1.5px solid rgba(196,198,207,0.5) !important;
    border-radius: 0.375rem !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    padding: 0.45rem 0.8rem !important;
    white-space: nowrap !important;
    box-shadow: none !important;
    transition: background 0.15s, border-color 0.15s !important;
    cursor: pointer !important;
}
#root [data-testid="stButton"] button:hover {
    background: #f2f4f6 !important;
    border-color: rgba(196,198,207,0.9) !important;
    color: #001731 !important;
}

/* Primary CTA (Run button) */
#root [data-testid="baseButton-primary"] button,
#root [data-testid="stButton"] button[data-testid="baseButton-primary"] {
    background: #E8643B !important;
    color: #fff !important;
    border: none !important;
    font-size: 0.85rem !important;
    font-weight: 700 !important;
    padding: 0.7rem 1.5rem !important;
    width: 100% !important;
    border-radius: 0.375rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}
#root [data-testid="baseButton-primary"] button:hover,
#root [data-testid="stButton"] button[data-testid="baseButton-primary"]:hover {
    background: #d4572f !important;
}
#root [data-testid="baseButton-primary"] button:disabled,
#root [data-testid="stButton"] button[data-testid="baseButton-primary"]:disabled {
    background: #c4c6cf !important;
    opacity: 0.6 !important;
}

/* ── Signal source chips container ── */
.nst-sources-wrap { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.5rem; }

/* ── Custom HTML classes ── */
.nst-helper {
    font-size: 0.75rem;
    color: #74777f;
    line-height: 1.45;
    margin-top: 0.4rem;
}
.nst-section-label {
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #001731;
    margin-bottom: 0.25rem;
}
.nst-section-desc {
    font-size: 0.82rem;
    color: #43474e;
    line-height: 1.55;
    margin-bottom: 0.8rem;
}
.nst-spacer {
    height: 1.75rem;
}
.nst-source-tag {
    display: inline-block;
    background: #e6e8ea;
    color: #43474e;
    padding: 0.3rem 0.65rem;
    border-radius: 0.25rem;
    font-size: 0.72rem;
    font-weight: 600;
}

/* ── Results ── */
.verdict-badge {
    display: inline-block; padding: 0.2rem 0.65rem; border-radius: 20px;
    font-size: 0.76rem; font-weight: 600; color: #fff; margin-bottom: 0.3rem;
}
.claim-type-tag {
    display: inline-block; background: #e6e8ea; color: #001731;
    padding: 0.12rem 0.45rem; border-radius: 4px; font-size: 0.7rem;
    font-weight: 500; margin-right: 0.22rem;
    text-transform: uppercase; letter-spacing: 0.04em;
}
.reasoning-text { font-size: 0.87rem; color: #43474e; line-height: 1.55; margin-top: 0.3rem; }
.signal-row     { font-size: 0.79rem; padding: 0.18rem 0; border-bottom: 1px solid #f0f0f0; color: #43474e; }
.error-box      {
    background: #fff3f0; border: 1px solid #b22200; border-radius: 0.375rem;
    padding: 0.5rem 0.75rem; font-size: 0.8rem; color: #7a2a1a; margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for _k, _v in [("result", None), ("running", False),
                ("company_domain_input", ""), ("competitors_input", "")]:
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Callbacks ─────────────────────────────────────────────────────────────────
def _on_company_name_change():
    name = st.session_state.get("company_name_input", "").strip()
    st.session_state.company_domain_input = (
        f"{name.lower().replace(' ','').replace(',','').replace('.','')}.com"
        if name else ""
    )


def _suggest_competitors(company_name: str) -> str:
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content":
                f"Name 4 direct competitors of {company_name}. "
                "Return only a comma-separated list of company names, nothing else."}],
        )
        raw = msg.content[0].text.strip()
        # Deduplicate, exclude subject company, enforce 4-cap
        company_lower = company_name.lower().strip()
        seen: set[str] = set()
        cleaned: list[str] = []
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if entry.lower() == company_lower:
                continue
            key = entry.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(entry)
            if len(cleaned) == 4:
                break
        return ", ".join(cleaned)
    except Exception:
        return ""


# ── Hero ──────────────────────────────────────────────────────────────────────
def render_hero():
    icon_uri = _b64_img(_ASSETS / "app-icon.png")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#001731 0%,#0d2c4d 100%);
                padding:2.5rem 3rem 2.2rem;border-radius:14px;margin-bottom:2rem">
        <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.75rem">
            <img src="{icon_uri}"
                 style="height:44px;width:44px;border-radius:10px;flex-shrink:0;box-shadow:0 0 0 1.5px rgba(255,255,255,0.3),0 2px 8px rgba(0,0,0,0.25)">
            <div style="font-size:0.7rem;font-weight:800;letter-spacing:0.2em;
                        text-transform:uppercase;color:#E8643B;
                        font-family:'DM Sans',sans-serif">PEMETIQ</div>
        </div>
        <div style="font-size:2.1rem;font-weight:700;color:#fff;
                    line-height:1.2;margin-bottom:0.6rem;font-family:'DM Sans',sans-serif">
            Manseil — Narrative Stress Test
        </div>
        <div style="font-size:0.92rem;color:rgba(255,255,255,0.8);line-height:1.65;
                    max-width:540px;font-family:'DM Sans',sans-serif">
            Paste an earnings transcript or investor memo and every claim gets
            stress-tested against public signals. Or enter a company name to run
            against their latest SEC filing.
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Form ──────────────────────────────────────────────────────────────────────
def render_input_form():

    # Apply any staged competitor suggestion before the widget renders
    if "_competitors_staged" in st.session_state:
        st.session_state.competitors_input = st.session_state.pop("_competitors_staged")

    # ── Row 1: Company name | Domain ──────────────────────────
    col_name, col_domain = st.columns(2, gap="medium")

    with col_name:
        company_name = st.text_input(
            "Company name",
            key="company_name_input",
            on_change=_on_company_name_change,
            placeholder="e.g. Salesforce, Stripe, Palantir",
        )

    with col_domain:
        company_domain = st.text_input(
            "Company domain",
            key="company_domain_input",
            placeholder="e.g. salesforce.com",
        )
        st.markdown(
            "<div class='nst-helper'>Auto-populated from company name. Override if needed.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='nst-spacer'></div>", unsafe_allow_html=True)

    # ── Analysis Mode ─────────────────────────────────────────
    st.markdown("""
    <div class="nst-section-label">Analysis mode</div>
    <div class="nst-section-desc">
        Choose what to test. <strong>Company name only</strong> fetches the company's latest SEC filing and stress-tests its stated claims. Paste a document to test a specific transcript or memo.
    </div>
    """, unsafe_allow_html=True)

    input_mode = st.segmented_control(
        "Analysis mode",
        options=["Company name only", "Earnings transcript", "Investor memo"],
        default="Company name only",
        label_visibility="collapsed",
        key="mode_radio",
    ) or "Company name only"

    input_text = None
    if input_mode != "Company name only":
        placeholders = {
            "Earnings transcript": "Paste the full earnings transcript here...",
            "Investor memo":       "Paste the investor memo or pitch deck text here...",
        }
        tab_paste, tab_upload = st.tabs(["Paste text", "Upload file (.txt / .pdf)"])

        with tab_paste:
            pasted = st.text_area(
                "Document text", height=140,
                placeholder=placeholders[input_mode],
                label_visibility="collapsed",
            )
            if pasted:
                input_text = pasted

        with tab_upload:
            uploaded = st.file_uploader("Upload", type=["txt", "pdf"],
                                        label_visibility="collapsed")
            if uploaded:
                if uploaded.type == "application/pdf":
                    try:
                        import io
                        import pdfminer.high_level as pdfminer  # type: ignore
                        input_text = pdfminer.extract_text(io.BytesIO(uploaded.read()))
                    except ImportError:
                        st.warning(
                            "PDF extraction requires pdfminer.six — "
                            "run: pip install pdfminer.six"
                        )
                else:
                    input_text = uploaded.read().decode("utf-8", errors="replace")
                if input_text:
                    st.caption(f"Loaded {len(input_text):,} characters from {uploaded.name}")

    st.markdown("<div class='nst-spacer'></div>", unsafe_allow_html=True)

    # ── Row 2: Company type | Competitors input | Suggest ─────
    # Flat 3-col layout [2, 3, 1] — no nesting, button gets ~120px
    col_type, col_comp, col_btn = st.columns([2, 3, 1], gap="medium")

    with col_type:
        # Spacer matches the height of the "Competitors" input label so the
        # segmented control and its helper text align with col_comp.
        st.markdown("<div style='height:1.1rem'></div>", unsafe_allow_html=True)
        company_type = st.segmented_control(
            "Company type",
            options=["Public", "Private"],
            default="Public",
            label_visibility="collapsed",
            key="type_radio",
        ) or "Public"
        type_helper = (
            "10-K / 10-Q filings pulled from SEC EDGAR."
            if company_type == "Public"
            else "News, trends, and non-SEC sources only."
        )
        st.markdown("<div style='height:1.1rem'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='nst-helper'>{type_helper}</div>",
            unsafe_allow_html=True,
        )

    with col_comp:
        competitors_raw = st.text_input(
            "Competitors",
            key="competitors_input",
            placeholder="e.g. HubSpot, ServiceNow, Zendesk",
        )
        st.markdown(
            "<div class='nst-helper'>Up to 4. Used for Google Trends comparison. Optional.</div>",
            unsafe_allow_html=True,
        )

    with col_btn:
        # Spacer to align button bottom with input bottom
        st.markdown("<div style='height:1.65rem'></div>", unsafe_allow_html=True)
        suggest_btn = st.button("Suggest", use_container_width=True)

    if suggest_btn and (company_name or "").strip():
        with st.spinner("Suggesting competitors…"):
            suggestion = _suggest_competitors(company_name.strip())
        if suggestion:
            st.session_state["_competitors_staged"] = suggestion
            st.rerun()

    st.markdown("<div class='nst-spacer'></div>", unsafe_allow_html=True)

    # ── Signal Sources ────────────────────────────────────────
    tags_html = "".join(
        f"<span class='nst-source-tag'>{s}</span>" for s in SIGNAL_SOURCES
    )
    st.markdown(f"""
    <div class="nst-section-label">Signal sources</div>
    <div class="nst-sources-wrap">{tags_html}</div>
    """, unsafe_allow_html=True)

    st.markdown("<div class='nst-spacer'></div>", unsafe_allow_html=True)

    return company_name, company_domain, company_type, input_mode, input_text, competitors_raw


# ── Results ───────────────────────────────────────────────────────────────────
def render_results(result: AnalysisResult):
    analysis  = result.analysis
    claims    = result.claims
    verdicts  = result.verdicts
    evidences = result.evidences
    coverage  = result.coverage

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Claims extracted", analysis.claim_count)
    c2.metric("Claims tested",    analysis.tested_count)
    # "Signal coverage" at 100% implies comprehensive narrative coverage — it doesn't.
    # It means X of the extracted claims had ≥1 matching signal. Renamed accordingly.
    strong   = coverage.get("strong_coverage", 0)
    partial  = coverage.get("partial_coverage", 0)
    total    = coverage.get("total_claims", 0)
    covered  = strong + partial
    c3.metric("Claims with signals", f"{covered} / {total}" if total else "—")

    # Source-coverage disclosure — show which of the 8 advertised sources contributed signals
    sources_fired = {_SOURCE_DISPLAY.get(sig.source, sig.source.value) for sig in result.signals}
    sources_silent = [s for s in SIGNAL_SOURCES if s not in sources_fired]
    if sources_silent:
        st.caption(
            f"Signals gathered from: {', '.join(sorted(sources_fired))}. "
            f"No data returned from: {', '.join(sources_silent)}."
        )

    info_msgs    = [e for e in result.errors if e.startswith("Auto-fetched")]
    no_src_msgs  = [e for e in result.errors if e.startswith("NO_SOURCE_TEXT:")]
    warn_msgs    = [e for e in result.errors
                    if not e.startswith("Auto-fetched") and not e.startswith("NO_SOURCE_TEXT:")]

    for msg in info_msgs:
        parts = msg.split(": ", 1)
        form  = parts[0].replace("Auto-fetched ", "")
        url   = parts[1] if len(parts) > 1 else ""
        st.info(f"Auto-fetched most recent **{form}** from SEC EDGAR: [{url}]({url})")

    if no_src_msgs:
        # Strip the prefix for display
        body = no_src_msgs[0].replace("NO_SOURCE_TEXT: ", "")
        st.warning(f"**No source document available.** {body}")
        return

    if warn_msgs:
        with st.expander(f"⚠️ {len(warn_msgs)} fetcher warning(s)", expanded=False):
            for err in warn_msgs:
                st.markdown(f"<div class='error-box'>{err}</div>", unsafe_allow_html=True)

    if not claims:
        st.info("No claims were extracted. Try pasting more detailed text.")
        return

    st.subheader("Claim-by-claim verdicts")
    st.caption("Sorted by significance — Contested and Partially Supported claims appear first.")

    verdict_filter = st.multiselect(
        "Filter by verdict",
        options=list(VERDICT_STYLES.keys()),
        default=list(VERDICT_STYLES.keys()),
        format_func=lambda v: VERDICT_STYLES[v][1],
    )

    signal_lookup = {sig.signal_id: sig for sig in result.signals}

    # Sort: contested findings first, supported last.
    # Within each verdict group: explicit before implicit, quantitative before qualitative.
    _VERDICT_ORDER = {
        "contested": 0, "partially_supported": 1, "insufficient_evidence": 2,
        "supported": 3, "not_testable": 4,
    }
    _SPECIFICITY_ORDER = {"quantitative": 0, "comparative": 1, "qualitative": 2}

    def _claim_sort_key(c):
        v = verdicts.get(c.claim_id)
        return (
            _VERDICT_ORDER.get(v.verdict.value if v else "insufficient_evidence", 2),
            int(c.is_implicit),
            _SPECIFICITY_ORDER.get(c.specificity.value, 2),
        )

    shown = 0
    for claim in sorted(claims, key=_claim_sort_key):
        verdict_obj = verdicts.get(claim.claim_id)
        verdict_key = verdict_obj.verdict.value if verdict_obj else "insufficient_evidence"
        if verdict_key not in verdict_filter:
            continue
        shown += 1
        _render_claim_card(claim, verdict_obj, evidences.get(claim.claim_id, []), signal_lookup)

    if shown == 0:
        st.info("No claims match the selected filters.")

    with st.expander(f"Raw signals gathered ({len(result.signals)})", expanded=False):
        for sig in sorted(result.signals, key=lambda s: s.reliability_tier):
            icon = "🔵" if sig.reliability_tier == 1 else "🟡" if sig.reliability_tier == 2 else "⚪"
            st.markdown(
                f"<div class='signal-row'>{icon} <b>{sig.signal_name}</b> "
                f"— {_format_value(sig.value)} "
                f"<span style='color:#aaa'>({sig.source.value})</span></div>",
                unsafe_allow_html=True,
            )


def _render_claim_card(claim, verdict_obj, claim_evidences, signal_lookup=None):
    bg, label = VERDICT_STYLES.get(
        verdict_obj.verdict.value if verdict_obj else "insufficient_evidence",
        ("#999", "Unknown"),
    )
    strength   = STRENGTH_LABELS.get(verdict_obj.evidence_strength.value if verdict_obj else "weak", "●○○")
    type_label = claim.claim_type.value.replace("_", " ").title()
    border     = CORAL if claim.is_implicit else TEAL

    with st.container():
        implicit_html = (
            f"<span class='claim-type-tag' style='background:#fff0ed;color:{CORAL}'>"
            f"implicit #{claim.implicit_pattern_id}</span>"
            if claim.is_implicit else ""
        )
        st.markdown(
            f"<div style='border-left:4px solid {border};padding:0.7rem 1rem;"
            f"background:#fafafa;border-radius:0 8px 8px 0;margin-bottom:0.1rem'>"
            f"<div style='margin-bottom:0.3rem'>"
            f"<span class='verdict-badge' style='background:{bg}'>{label}</span>"
            f"<span style='font-size:0.77rem;color:#888;margin-left:0.4rem'>Evidence: {strength}</span>"
            f"</div>"
            f"<div style='margin-bottom:0.3rem'>"
            f"<span class='claim-type-tag'>{type_label}</span>"
            f"<span class='claim-type-tag'>{claim.temporal_framing.value}</span>"
            f"<span class='claim-type-tag'>{claim.specificity.value}</span>"
            f"{implicit_html}</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{claim.assertion}**")
        if verdict_obj and verdict_obj.reasoning:
            st.markdown(
                f"<div class='reasoning-text'>{verdict_obj.reasoning}</div>",
                unsafe_allow_html=True,
            )

    if claim_evidences:
        with st.expander("Signal breakdown", expanded=False):
            for ev in claim_evidences:
                icon = {"supporting": "✅", "contradicting": "❌", "insufficient": "⚪"}.get(
                    ev.verdict.value, "⚪")
                sig = (signal_lookup or {}).get(ev.signal_id)
                sig_label = _signal_display_name(sig.signal_name) if sig else "Unknown signal"
                st.markdown(
                    f"<div class='signal-row'>{icon} <b>{sig_label}</b> — {ev.reasoning}</div>",
                    unsafe_allow_html=True,
                )


def _format_value(value) -> str:
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in list(value.items())[:3]]
        return "{" + ", ".join(parts) + ("…" if len(value) > 3 else "") + "}"
    if isinstance(value, float): return f"{value:,.2f}"
    if isinstance(value, int):   return f"{value:,}"
    return str(value)[:120]


# ── Footer ────────────────────────────────────────────────────────────────────
def render_footer():
    logo_uri = _b64_img(_ASSETS / "primary-logo.png")
    st.markdown(f"""
    <div style="margin-top:4rem;padding:2rem 0 1.5rem;
                border-top:1px solid #e2e4e8;text-align:center">
        <img src="{logo_uri}"
             style="height:28px;opacity:0.85;margin-bottom:0.75rem">
        <div style="font-size:0.75rem;color:#9aa3ac;font-family:'DM Sans',sans-serif">
            © 2026 Pemetiq · All signals sourced from public data
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    render_hero()

    company_name, company_domain, company_type_str, input_mode, input_text, competitors_raw = (
        render_input_form()
    )

    run_btn = st.button(
        "Run stress test",
        type="primary",
        disabled=not (company_name or "").strip() or st.session_state.running,
        use_container_width=True,
    )

    if run_btn and (company_name or "").strip():
        st.session_state.running = True
        st.session_state.result  = None

        progress_bar  = st.progress(0.0)
        progress_text = st.empty()

        def _update_progress(label: str, pct: float) -> None:
            progress_bar.progress(pct)
            progress_text.markdown(
                f"<div style='font-size:0.85rem;color:#43474e;margin-top:0.25rem'>{label}</div>",
                unsafe_allow_html=True,
            )

        try:
            _update_progress("Resolving company…", 0.02)
            cik, ticker = None, None
            if company_type_str == "Public":
                cik, ticker = lookup_cik(company_name.strip())

            domain    = (company_domain or "").strip() or \
                        f"{company_name.lower().replace(' ','')}.com"
            entity_id = company_name.lower().strip().replace(" ", "_")

            company = Company(
                entity_id=entity_id, name=company_name.strip(),
                ticker=ticker, cik=cik, domain=domain,
                company_type=(CompanyType.public if company_type_str == "Public"
                              else CompanyType.private),
            )
            competitors = (
                [c.strip() for c in competitors_raw.split(",") if c.strip()]
                if competitors_raw else None
            )
            result = run_analysis(
                company=company,
                input_text=input_text or None,
                input_type={
                    "Company name only": InputType.company_name,
                    "Earnings transcript": InputType.earnings_transcript,
                    "Investor memo":       InputType.investor_memo,
                }[input_mode],
                competitors=competitors,
                progress_callback=_update_progress,
            )
            st.session_state.result = result

        except RuntimeError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Analysis failed: {e}")
        finally:
            st.session_state.running = False
            progress_bar.empty()
            progress_text.empty()
        st.rerun()

    if st.session_state.result:
        render_results(st.session_state.result)

    render_footer()


if __name__ == "__main__":
    main()
