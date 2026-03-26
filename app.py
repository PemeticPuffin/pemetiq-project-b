"""
Pemetiq Narrative Stress Test — Streamlit UI
Run: streamlit run app.py
"""
from __future__ import annotations

import os

import anthropic
import streamlit as st

st.set_page_config(
    page_title="Narrative Stress Test · Pemetiq",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from schema.enums import CompanyType, InputType
from schema.models import Company
from pipeline.orchestrator import AnalysisResult, run_analysis
from utils.company_lookup import lookup_cik

NAVY  = "#0E3B54"
TEAL  = "#1A5C6A"
CORAL = "#E8643B"

SIGNAL_SOURCES = [
    "SEC EDGAR", "Google Trends", "GitHub", "App Store",
    "Job postings", "Wayback Machine", "GDELT", "Wappalyzer",
]

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
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap');

/* ── Base ── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="block-container"] {
    font-family: 'DM Sans', sans-serif !important;
    background: #FAFBFC !important;
    color: #333 !important;
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
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    color: #0E3B54 !important;
}

/* ── Text inputs ── */
[data-testid="stTextInput"] input {
    border: 1px solid #D0D7DD !important;
    border-radius: 6px !important;
    padding: 0.6rem 0.8rem !important;
    font-size: 0.88rem !important;
    color: #333 !important;
    background: #fff !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-testid="stTextInput"] input:hover  { border-color: #A8B8C2 !important; }
[data-testid="stTextInput"] input:focus  {
    border-color: #1A5C6A !important;
    box-shadow: 0 0 0 2.5px rgba(26, 92, 106, 0.12) !important;
}
[data-testid="stTextInput"] input::placeholder { color: #B0BAC2 !important; }

/* ── Text area ── */
[data-testid="stTextArea"] textarea {
    border: 1px solid #D0D7DD !important;
    border-radius: 6px !important;
    font-size: 0.86rem !important;
    transition: border-color 0.18s !important;
}
[data-testid="stTextArea"] textarea:focus {
    border-color: #1A5C6A !important;
    box-shadow: 0 0 0 2px rgba(26,92,106,0.14) !important;
}
[data-testid="stTextArea"] textarea::placeholder { color: #B0BAC2 !important; }

/* ══════════════════════════════════════════════════════
   ANALYSIS MODE — 3-card button style (all st.radio)
   Active card: navy border. Inactive: light gray border.
══════════════════════════════════════════════════════ */
[data-testid="stRadio"] > div:last-child {
    display: flex !important;
    flex-direction: row !important;
    background: none !important;
    padding: 0 !important;
    border-radius: 0 !important;
    gap: 0.75rem !important;
}
[data-testid="stRadio"] > div:last-child > label {
    flex: 1 1 0 !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    border: 2px solid #E2E6EA !important;
    border-radius: 8px !important;
    padding: 0.9rem 0.75rem !important;
    background: #fff !important;
    cursor: pointer !important;
    transition: border-color 0.15s ease !important;
    box-shadow: none !important;
}
[data-testid="stRadio"] > div:last-child > label:hover {
    border-color: #A8B8C2 !important;
    background: #F7F8FA !important;
}
[data-testid="stRadio"] > div:last-child > label:has(input:checked) {
    border-color: #0E3B54 !important;
    border-width: 2px !important;
    background: #fff !important;
    box-shadow: none !important;
}
[data-testid="stRadio"] > div:last-child > label > div:first-child { display: none !important; }
[data-testid="stRadio"] > div:last-child > label > div:last-child {
    display: flex !important;
    justify-content: center !important;
}
[data-testid="stRadio"] > div:last-child > label > div:last-child p {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    color: #6B7580 !important;
    margin: 0 !important;
    text-align: center !important;
    white-space: nowrap !important;
}
[data-testid="stRadio"] > div:last-child > label:has(input:checked) > div:last-child p {
    color: #0E3B54 !important;
}

/* Company type radio inside columns — keep same card style,
   but smaller padding and left-aligned text */
[data-testid="column"] [data-testid="stRadio"] > div:last-child {
    gap: 0.5rem !important;
}
[data-testid="column"] [data-testid="stRadio"] > div:last-child > label {
    flex: none !important;
    padding: 0.5rem 0.9rem !important;
    justify-content: flex-start !important;
}
[data-testid="column"] [data-testid="stRadio"] > div:last-child > label > div:last-child p {
    font-size: 0.88rem !important;
    text-align: left !important;
}

/* ══════════════════════════════════════════════════════
   BUTTONS
   Use #root for maximum specificity to beat Emotion CSS.
   Step 1: default all st.button() to ghost/secondary style.
   Step 2: override Run (primary) with extra attr selector
           for higher specificity — comes last in cascade.
══════════════════════════════════════════════════════ */

/* Step 1 — ghost style for ALL st.button() calls */
#root [data-testid="stButton"] button {
    background: #f0f2f4 !important;
    color: #0E3B54 !important;
    border: 1.5px solid #C8D3DA !important;
    border-radius: 6px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 0.45rem 0.8rem !important;
    white-space: nowrap !important;
    box-shadow: none !important;
    transition: background 0.15s, border-color 0.15s !important;
    cursor: pointer !important;
}
#root [data-testid="stButton"] button:hover {
    background: #e2e7ec !important;
    border-color: #9AAAB5 !important;
    color: #0E3B54 !important;
}

/* Step 2 — primary CTA override.
   In Streamlit 1.55 the testid sits on the WRAPPER div, not the button element,
   so we target [data-testid="baseButton-primary"] as an ancestor. */
#root [data-testid="baseButton-primary"] button,
#root [data-testid="stButton"] button[data-testid="baseButton-primary"] {
    background: #E8643B !important;
    color: #fff !important;
    border: none !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.5rem !important;
    width: 100% !important;
    border-radius: 6px !important;
}
#root [data-testid="baseButton-primary"] button:hover,
#root [data-testid="stButton"] button[data-testid="baseButton-primary"]:hover {
    background: #D4572F !important;
}
#root [data-testid="baseButton-primary"] button:disabled,
#root [data-testid="stButton"] button[data-testid="baseButton-primary"]:disabled {
    background: #BEC8CE !important;
    opacity: 0.7 !important;
}

/* ── Signal source tags container ── */
.nst-sources-wrap { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.4rem; }

/* ── Custom HTML classes ── */
.nst-helper {
    font-size: 0.72rem;
    color: #8A939C;
    line-height: 1.45;
    margin-top: 0.35rem;
}
.nst-section-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #0E3B54;
    margin-bottom: 0.2rem;
}
.nst-section-desc {
    font-size: 0.78rem;
    color: #6B7580;
    line-height: 1.5;
    margin-bottom: 0.7rem;
}
.nst-divider {
    border: none;
    border-top: 1px solid #E2E6EA;
    margin: 0.5rem 0 1.5rem;
}
.nst-source-tag {
    display: inline-block;
    background: #EAF0F2;
    color: #4A6A74;
    padding: 0.2rem 0.5rem;
    border-radius: 3px;
    font-size: 0.66rem;
    font-weight: 500;
    margin: 0.1rem 0.15rem 0.1rem 0;
}

/* ── Results ── */
.verdict-badge {
    display: inline-block; padding: 0.2rem 0.65rem; border-radius: 20px;
    font-size: 0.76rem; font-weight: 600; color: #fff; margin-bottom: 0.3rem;
}
.claim-type-tag {
    display: inline-block; background: #EAF0F2; color: #0E3B54;
    padding: 0.12rem 0.45rem; border-radius: 4px; font-size: 0.7rem;
    font-weight: 500; margin-right: 0.22rem;
    text-transform: uppercase; letter-spacing: 0.04em;
}
.reasoning-text { font-size: 0.87rem; color: #333; line-height: 1.55; margin-top: 0.3rem; }
.signal-row     { font-size: 0.79rem; padding: 0.18rem 0; border-bottom: 1px solid #f0f0f0; color: #555; }
.error-box      {
    background: #fff3f0; border: 1px solid #E8643B; border-radius: 6px;
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
        return msg.content[0].text.strip()
    except Exception:
        return ""


# ── Hero ──────────────────────────────────────────────────────────────────────
def render_hero():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#0E3B54 0%,#1A5C6A 60%,#2A7A8A 100%);
                padding:2.25rem 2.5rem 2rem;margin-bottom:1.75rem">
        <div style="font-size:0.72rem;font-weight:700;letter-spacing:0.2em;
                    text-transform:uppercase;color:#E8643B;margin-bottom:0.55rem;
                    font-family:'DM Sans',sans-serif">PEMETIQ</div>
        <div style="font-size:1.75rem;font-weight:700;color:#fff;
                    line-height:1.2;margin-bottom:0.6rem;font-family:'DM Sans',sans-serif">
            Narrative Stress Test
        </div>
        <div style="font-size:0.9rem;color:rgba(255,255,255,0.65);line-height:1.55;
                    max-width:520px;font-family:'DM Sans',sans-serif">
            Enter a company name — or paste an earnings transcript or investor memo.
            Every claim gets extracted and tested against public signals.
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Form ──────────────────────────────────────────────────────────────────────
def render_input_form():

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

    st.markdown("<hr class='nst-divider'>", unsafe_allow_html=True)

    # ── Analysis Mode ─────────────────────────────────────────
    st.markdown("""
    <div class="nst-section-label">Analysis mode</div>
    <div class="nst-section-desc">
        Choose what to test. <strong>Company name only</strong> infers claims from public signals.
        Paste a document to test the specific claims made in it.
    </div>
    """, unsafe_allow_html=True)

    input_mode = st.radio(
        "Analysis mode",
        options=["Company name only", "Earnings transcript", "Investor memo"],
        horizontal=True,
        label_visibility="collapsed",
        key="mode_radio",
    )

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

    st.markdown("<hr class='nst-divider'>", unsafe_allow_html=True)

    # ── Row 2: Company type | Competitors input | Suggest ─────
    # Flat 3-col layout [2, 3, 1] — no nesting, button gets ~120px
    col_type, col_comp, col_btn = st.columns([2, 3, 1], gap="medium")

    with col_type:
        company_type = st.radio(
            "Company type",
            options=["Public", "Private"],
            horizontal=True,
            key="type_radio",
        )
        type_helper = (
            "10-K / 10-Q filings pulled from SEC EDGAR."
            if company_type == "Public"
            else "News, trends, and non-SEC sources only."
        )
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
            st.session_state.competitors_input = suggestion
            st.rerun()

    st.markdown("<hr class='nst-divider'>", unsafe_allow_html=True)

    # ── Signal Sources ────────────────────────────────────────
    tags_html = "".join(
        f"<span class='nst-source-tag'>{s}</span>" for s in SIGNAL_SOURCES
    )
    st.markdown(f"""
    <div class="nst-section-label">Signal sources</div>
    <div class="nst-sources-wrap">{tags_html}</div>
    """, unsafe_allow_html=True)

    st.markdown("<hr class='nst-divider'>", unsafe_allow_html=True)

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
    c3.metric("Signal coverage",  f"{coverage.get('coverage_pct', 0):.0f}%")

    info_msgs = [e for e in result.errors if e.startswith("Auto-fetched")]
    warn_msgs = [e for e in result.errors if not e.startswith("Auto-fetched")]

    for msg in info_msgs:
        parts = msg.split(": ", 1)
        form  = parts[0].replace("Auto-fetched ", "")
        url   = parts[1] if len(parts) > 1 else ""
        st.info(f"Auto-fetched most recent **{form}** from SEC EDGAR: [{url}]({url})")

    if warn_msgs:
        with st.expander(f"⚠️ {len(warn_msgs)} fetcher warning(s)", expanded=False):
            for err in warn_msgs:
                st.markdown(f"<div class='error-box'>{err}</div>", unsafe_allow_html=True)

    if not claims:
        st.info("No claims were extracted. Try pasting more detailed text.")
        return

    st.subheader("Claim-by-claim verdicts")
    verdict_filter = st.multiselect(
        "Filter by verdict",
        options=list(VERDICT_STYLES.keys()),
        default=list(VERDICT_STYLES.keys()),
        format_func=lambda v: VERDICT_STYLES[v][1],
    )

    shown = 0
    for claim in sorted(claims, key=lambda c: (c.is_implicit, c.claim_type.value)):
        verdict_obj = verdicts.get(claim.claim_id)
        verdict_key = verdict_obj.verdict.value if verdict_obj else "insufficient_evidence"
        if verdict_key not in verdict_filter:
            continue
        shown += 1
        _render_claim_card(claim, verdict_obj, evidences.get(claim.claim_id, []))

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


def _render_claim_card(claim, verdict_obj, claim_evidences):
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
                st.markdown(
                    f"<div class='signal-row'>{icon} <b>{ev.signal_id[:8]}…</b> — {ev.reasoning}</div>",
                    unsafe_allow_html=True,
                )


def _format_value(value) -> str:
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in list(value.items())[:3]]
        return "{" + ", ".join(parts) + ("…" if len(value) > 3 else "") + "}"
    if isinstance(value, float): return f"{value:,.2f}"
    if isinstance(value, int):   return f"{value:,}"
    return str(value)[:120]


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

        with st.spinner("Gathering signals and extracting claims…"):
            try:
                cik, ticker = None, None
                if company_type_str == "Public":
                    with st.spinner("Resolving EDGAR CIK…"):
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
                )
                st.session_state.result = result

            except RuntimeError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Analysis failed: {e}")
            finally:
                st.session_state.running = False
        st.rerun()

    if st.session_state.result:
        render_results(st.session_state.result)


if __name__ == "__main__":
    main()
