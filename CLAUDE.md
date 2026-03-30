# Pemetiq Project B — Manseil

## What This Is
A tool where a user inputs a company (public or private) or pastes a pitch deck / investor memo / earnings transcript. The tool pulls public signals and systematically tests narrative claims against observable evidence. Output is claim-by-claim: "The company says X. The evidence says Y. Confidence: Z."

## How It Differs from Project A (CI Autopilot)
- Project A starts from data and synthesizes upward → "What should I know?"
- Project B starts from claims and tests downward → "Should I believe what they're telling me?"
- Shared signal schema is planned for future interop, but they run independently in v1.

## Owner
Aaron, founder of Pemetiq. 15+ years data science/analytics at director+ level, Gartner vendor intelligence background, domains: asset mgmt, finserv, retail, SaaS. Python/R/SQL native. Directs Claude Code as engineering tool rather than coding manually.

## Brand
- Colors: Navy #001731 (Atlantic Navy Blue), Teal #1A5C6A, Coral #E8643B (accent), Run/Alert #b22200 (Coral Jasper)
- Typeface: DM Sans
- Mascot: Geometric puffin (navy body, coral beak)

## Tech Stack (Expected)
- Streamlit (frontend, consistent with Project A)
- Python
- Anthropic API (Claude Sonnet for claim extraction + evaluation)
- Free-tier data APIs (see Data Sources below)

## Current Phase: Phase 3 Complete — Ready for UI Polish + Deployment

### What's Been Decided (Phases 1 + 2 Complete)

**Claim Taxonomy (5 categories for MVP):**
1. Growth / Traction
2. Market Position / Competition
3. Team / Execution
4. Product / Technology
5. Unit Economics (public companies only)

Category 6 (Strategic Narrative — moats, timing, tailwinds) is deferred from v1.

**Claim Decomposition Framework:**
Every claim extracted with: Assertion, Claim Type, Specificity (Quantitative/Comparative/Qualitative), Testability (Yes/Partial/No), Temporal Framing (Past/Present/Forward), Attribution Clarity (Clear/Ambiguous/Unverifiable).

Framework also detects implicit claims — things the narrative assumes without stating (26 patterns defined, see BUILD_LOG.md for full list).

**Evidence Mapping (two layers):**
- Layer 1: Claim type → Signal family (domain judgment — static)
- Layer 2: Signal → Source + Method (engineering — swappable)

**Confidence Scoring:**
Three dimensions: Evidence Strength, Claim Specificity, Source Reliability.
Five-level verdict: Supported / Partially Supported / Contested / Insufficient Evidence / Not Testable.
No single numeric score — structured verdict with reasoning.

**Connected Tooling Strategy:**
Design Project B's data model to be compatible with Project A (shared entity model: company → signals → sources → timestamps). Don't build shared infra yet, but use a consistent signal schema.

### Phase 2 Complete — Data Sources Confirmed

| Signal Type | Source | Status | Tier |
|---|---|---|---|
| SEC filings | EDGAR (submissions, XBRL, 8-K search) | Confirmed | 1 |
| Search trends | Google Trends / pytrends | Confirmed | 2 |
| Job postings | Adzuna (key registered) | Confirmed | 2 |
| Tech stack | Wappalyzer OSS (Node.js subprocess) | Confirmed | 3 |
| Pricing history | Wayback Machine CDX | Confirmed (URL discovery step required) | 3 |
| News/press | GDELT (async only, title-match filter required) | Confirmed | 3 |
| App store | Apple App Store / iTunes Search API | Confirmed | 2 |
| GitHub activity | GitHub API (free auth token required for prod) | Confirmed | 2 |
| Funding history | Crunchbase | Deferred — $29/mo; EDGAR S-1 covers public cos | — |
| Web traffic | SimilarWeb | Dropped — $14K+/yr enterprise | — |
| Review sites | G2 / Capterra | Dropped — blocked/requires key | — |
| Patent filings | USPTO PatentsView | Dropped — 403 blocked; proxy via GitHub | — |

### Phase 3 Build Sequence — ALL COMPLETE ✅
1. ✅ Data layer — all 8 fetchers built (edgar, adzuna, appstore, gdelt, github, google_trends, wappalyzer, wayback)
2. ✅ Claim extraction — Claude tool-use call, structured output, 20-claim cap
3. ✅ Evidence mapper — static ClaimType → SignalType map
4. ✅ Verdict engine — Claude call per claim, per-signal breakdown + synthesis verdict
5. ✅ Spend tracker — daily ledger, would_exceed check, status() for UI
6. ✅ Streamlit UI — full app.py with brand CSS, hero, form, claim-by-claim results
7. ✅ GDELT async — background thread, joins after primary fetchers

### Test Suite — ALL PASSING ✅
- 103 unit tests (no API calls): `pytest tests/`
- 4 live smoke tests (~$0.03/run): `pytest -m smoke -s`
- Smoke test validated 2026-03-24 against Salesforce (CRM):
  - 16 claims extracted (9 explicit, 7 implicit)
  - 68.8% signal coverage
  - Correctly contested the "20% YoY growth" claim vs EDGAR's 9.6% full-year figure

### Remaining Before Launch
1. **UI styling pass** — `UI updates - 3.22.26/NST_UI_SPEC.md` defines the target design; `nst-start-screen.html` is the reference. Current app.py CSS needs to be reconciled against it.
2. **Deployment** — push to private GitHub repo → connect to Streamlit Community Cloud. Secrets go in Streamlit Cloud secrets management (same pattern as Project A).
3. **server.py** — Flask server is a dead detour. Delete it (confirm with Aaron first). The one unique feature it has — spend alert emails — can be added to the Streamlit sidebar or SpendTracker if needed.
4. **Project A parity check** — both apps launch simultaneously. Confirm Project A is in equivalent shape before deploying either.

### Signal Schema (defined in BUILD_LOG)
6 entities: Company, Signal, Claim, Evidence, ClaimVerdict, Analysis
3 reliability tiers. See BUILD_LOG.md Phase 2 close-out entry for full spec.

### Daily Spend Limit
SpendTracker class — JSON ledger, pre-run check, post-run record, Streamlit sidebar meter.
Env var: `DAILY_SPEND_LIMIT_USD` (default $5/day). Anthropic Console monthly cap as backstop.

### Cost Constraints
- MVP cost envelope: ~$50-100/mo (mostly Anthropic API)
- No fixed data subscriptions required at launch
- Expensive sources (SimilarWeb API, Semrush enterprise) deferred until paying users justify cost

## Build Log
See BUILD_LOG.md for full decision history with rationale and alternatives considered.

## Key Principles
- Domain judgment must be embedded (not just "AI reads your deck")
- At least one non-AI layer of value (claim taxonomy, evidence mapping, confidence methodology)
- Cannot resemble vendor evaluation or software advisory (employer conflict)
- Polish over technical experimentation when forced to choose
- Design for platform interop with Project A, but don't build shared infra yet
- Free-tier data first, upgrade when unit economics support it
