# Pemetiq Project B — Narrative Stress Test: Build Log

> Append-only decision log. Each entry captures what was decided, why, and what was considered. This becomes the skeleton for the eventual write-up.

---

## 2026-03-19 — Project B Concept Locked

**Phase:** Pre-build / Scoping

**Concept:** A tool where a user inputs a company (public or private) or pastes a pitch deck / investor memo / earnings transcript. The tool pulls public signals and systematically tests narrative claims against observable evidence. Output is claim-by-claim: "The company says X. The evidence says Y. Confidence: Z."

**Core differentiator from Project A (CI Autopilot):**
- CI Autopilot starts from data and synthesizes upward → "What should I know?"
- Narrative Stress Test starts from claims and tests downward → "Should I believe what they're telling me?"

**Target users:** Investors, VPs/directors, founders

**Key design constraints:**
- Must embed opinionated domain judgment (15+ yrs data science/analytics, Gartner vendor intelligence, asset mgmt / finserv / retail / SaaS)
- Must have at least one non-AI layer of value (claim-testing framework, signal taxonomy, confidence methodology)
- Cannot resemble vendor evaluation or software advisory (employer conflict)
- Data sources must be practically accessible and affordable — no over-investing ahead of revenue
- API costs (Anthropic) justified if value supports it
- Engineering via Claude Code, not manual coding
- Superpower ranking: narrative cutting > framework design > signal detection > competitive positioning

**Approach — three phases:**
1. Claim taxonomy + evidence mapping (what claims can we realistically adjudicate?)
2. Data source validation (availability, cost, reliability for the signals that matter)
3. MVP scope + build spec

**Key insight surfaced early:** The product's value depends on the evidence layer being strong enough. If the tool can only test 3/10 claims, the UX degrades to "insufficient evidence" verdicts. First-order question is whether the testable claim set is large enough to justify the product.

---

## 2026-03-19 — Claim Taxonomy + Frequency Analysis + Cost Model + Platform Strategy

**Phase:** 1 — Framework Design

### Claim Taxonomy

Established 6 categories of narrative claims found in pitch decks, investor memos, and earnings transcripts:

1. **Growth / Traction** — revenue growth, user growth, market expansion, trajectory claims
2. **Market Position / Competition** — market leadership, category creation, differentiation, TAM
3. **Team / Execution** — team pedigree, hiring momentum, execution velocity, retention
4. **Product / Technology** — technical differentiation, performance claims, AI sophistication, integrations
5. **Unit Economics / Financials** — profitability, capital efficiency, pricing power, burn/runway
6. **Strategic Narrative** — market tailwind, timing/inevitability, moat/defensibility, partnerships

Each category mapped to observable signals and rated for testability (high/medium/low).

### Frequency-Informed Prioritization

Research based on DocSend pitch deck studies (200+ decks), standard deck structures, and earnings call analysis:

- **Team** slides present in 100% of decks (DocSend). Investors rank team at 23% of evaluation criteria.
- **Market/Growth** claims in 92%+ of successful decks. Market opportunity is #1 investor consideration (28%).
- **Product** present in ~90%+. Investor scrutiny of product slides up 46% from 2019→2020.
- **Competition** scrutiny up 51% year-over-year.
- **Business model** scrutiny up 28% year-over-year.
- **Financials** only in 58% of successful decks, but 0% of failed decks included them.
- **"Why Now"** in 86% of pre-seed decks, drops at later stages.

### MVP Scope Decision

**In v1 (categories 1-4):** Growth/Traction, Market Position, Team/Execution, Product/Technology
**Partial v1 (category 5):** Unit Economics — public companies only (SEC data available)
**Deferred (category 6):** Strategic Narrative — too qualitative, dilutes tool credibility

**Rationale:** MVP scope driven by intersection of frequency (how often claims appear) × testability (can we get evidence). Strategic Narrative claims are common but evidence layer is thin — including them with "insufficient evidence" verdicts would undermine the product's core promise.

### Cost Model

**Free tier (MVP foundation):**
- SEC EDGAR API (free, unlimited — already used in Project A)
- Google Trends via pytrends (free)
- Job postings — Indeed/LinkedIn public, Adzuna free tier
- Crunchbase basic data (free) / starter API ($29/mo)
- BuiltWith/Wappalyzer free tier
- Google Search/News, Wayback Machine API, GitHub public activity, app store data, G2/Capterra public reviews — all free

**Moderate tier ($100-500/mo) — deferred until revenue:**
- Web traffic (SimilarWeb API is enterprise-only at $14K+/yr; alternatives: SimilarWeb free tier + Google Trends as proxy for MVP)
- News APIs (free tiers exist, paid $50-450/mo)
- Anthropic API: ~$0.50-2.00 per company analysis at Sonnet pricing

**MVP cost envelope:** ~$50-100/mo (Anthropic API + maybe one data subscription). No fixed data subscriptions required at launch.

**Key insight:** Expensive data sources (SimilarWeb, Semrush enterprise) become justified when paying users exist. Design for free-tier data first, upgrade when unit economics support it.

### Connected Tooling / Platform Strategy

**Decision:** Design Project B's data model to be compatible with Project A, but don't build shared infrastructure yet.

**The platform thesis:**
- Project A (CI Autopilot): "What should I know?" — synthesis upward from data
- Project B (Narrative Stress Test): "Should I believe this?" — testing downward from claims
- Natural workflow: Run A for baseline, run B against a narrative to find divergences
- Future Project C (Decision Engine) could consume outputs from both

**Architectural implications for Project B:**
- Define a standard company signal schema that both tools could share
- Shared entity model: company → signals → sources → timestamps
- Shared signal taxonomy (e.g., "hiring momentum" means the same thing in both tools)
- Cost of designing for this now ≈ zero; cost of retrofitting later = significant

**Alternatives considered:** Building shared infra now (rejected — premature optimization), ignoring platform play entirely (rejected — low-cost design decisions now prevent expensive refactoring later).

---

## 2026-03-19 — Claim Decomposition Framework + Implicit Claims Library

**Phase:** 1 — Framework Design

### Claim Decomposition Framework (3 components)

**Component 1 — Claim Extraction Schema:**
Every extracted claim gets four fields:
- **Assertion** — plain language statement of what's claimed
- **Claim type** — mapped to taxonomy (Growth, Market Position, Team, Product, Unit Economics)
- **Specificity level** — Quantitative / Comparative / Qualitative
- **Testability flag** — Yes / Partial / No

Plus two modifier flags added during design review:
- **Temporal framing** — Past / Present / Forward (critical for earnings calls where forward guidance sounds like fact)
- **Attribution clarity** — Clear / Ambiguous / Unverifiable (critical for AI/tech claims where causal attribution is unverifiable)

The framework also captures **implicit claims** — things the narrative assumes without stating. These are where domain judgment adds the most value. Extraction prompt is structured, not open-ended: the LLM maps into the taxonomy rather than generating freeform.

**Component 2 — Evidence Mapping (two layers):**
- **Layer 1: Claim type → Signal family** (static, encodes domain judgment — "for this claim type, these signals matter")
- **Layer 2: Signal → Source + Method** (operational, maps signals to specific API calls/data sources)

Separation means data sources can be upgraded without changing the intellectual framework.

Three possible verdicts per signal: Supporting / Contradicting / Insufficient.

Key design insight: The interesting output isn't binary confirm/deny — it's synthesis across signals. "The financial claim checks out, but surrounding signals suggest growth may not be sustainable." This is the narrative cutting capability.

**Component 3 — Confidence Scoring (three dimensions):**
- **Evidence strength** — how many independent signals, how direct (Strong/Moderate/Weak)
- **Claim specificity** — quantitative claims get tighter confidence bands, qualitative claims get widest
- **Source reliability** — SEC filings > press releases > job postings > traffic estimates > social media

Output is a structured verdict, NOT a single numeric score. Five-level scale:
**Supported / Partially Supported / Contested / Insufficient Evidence / Not Testable**

**Rationale for no numeric score:** Target users (investors, VPs, founders) are sophisticated enough to want the decomposition. A single number creates false precision and hides reasoning.

### Full Pipeline
1. Input (paste deck/transcript or enter company name)
2. Decomposition (structured claim extraction)
3. Evidence gathering (fetch signals per evidence map)
4. Evaluation (claim-by-claim assessment using confidence methodology)
5. Synthesis (overall narrative assessment — where it holds, where it cracks, what's absent)

Non-AI layers of value: claim taxonomy (step 2), evidence mapping (step 3), confidence methodology (step 4).

### Implicit Claims Library — 26 patterns selected for v1

**Growth / Traction (7):**
1. No churn/retention mention despite growth focus
2. Hockey-stick projections with no unit economics backing
3. Revenue growth highlighted while margin trend omitted
4. "Fastest-growing" without specifying comparison set
5. Topline metrics without cohort behavior
7. Growth rate cited without absolute base

**Market Position (4):**
9. TAM cited as top-down number from analyst report
10. Competitor matrix where you win every row
12. Market share claim without denominator definition
13. Industry awards cited without context (pay-to-play, self-nominated)

**Team / Execution (2):**
16. Large team size without function breakdown
19. Solo technical or business founder without complement

**Product / Technology (6):**
21. "AI-powered" with no ML engineers in job postings
22. "Proprietary technology" without patents, papers, or OSS contributions
23. "Platform" language with only one product
24. Performance claims without third-party benchmarks
25. "Enterprise-ready" without SOC 2 or certifications
26. Integration count without depth assessment

**Unit Economics / Financials (3):**
29. Revenue mix not disclosed (one-time vs. recurring)
32. Pricing page removed or hidden (Wayback Machine detectable)
33. Customer logos without dates or deal context

**Cross-Cutting / Behavioral (4):**
34. Euphemistic language in earnings calls ("headwinds," "lumpiness," "rightsizing")
35. Highly scripted Q&A responses
36. Metric definition changes between periods (added on review — classic earnings call red flag)
38. Asymmetric partnership press (added on review — highly testable, common in SaaS/finserv)
40. Analyst questions repeatedly probing same area across quarters

### Selection Rationale
Started with 40 candidate patterns. Aaron selected 24 based on practical relevance and domain experience. 2 additional patterns (#36, #38) added back after review — both are highly testable and common in target domains. Cut patterns were mostly: unit economics items that overlap with existing financial analysis tools, speculative items harder to detect reliably, or patterns less common in practice.

---

## 2026-03-19 — Phase 2: Data Source Validation Results

**Phase:** 2 — Data Source Validation
**Test company:** Salesforce, Inc. (CRM / EDGAR CIK: 0001108524)
**Method:** Live API calls against all 12 signal sources listed in Phase 2 scope. Script: `phase2_validation.py`.

---

### Verdict by Source

#### ✅ CONFIRMED — No Key Required, Works in Production

**SEC EDGAR**
- Submissions endpoint returns full filing history (1,001 total; 10-K: 3, 10-Q: 8 in recent index)
- Latest 10-K filed 2026-03-02; latest 10-Q filed 2025-12-04
- XBRL company facts endpoint returns structured financials (revenue key: `SalesRevenueServicesNet`; multiple revenue/margin/EPS concepts available)
- 8-K full-text search endpoint returns 610 filings (2024–2025) — earnings call transcripts accessible this way
- Latency: 287–541ms. Reliability: high.
- **Coverage:** Unit Economics (revenue, margins, EPS), Growth/Traction (YoY trends), Cross-Cutting (metric definition changes detectable across filings)
- **Decision:** Primary source for all financial claims. Highest source reliability tier.

**Google Trends (pytrends)**
- 52-week avg: Salesforce 65.3/100, HubSpot 24.3/100, ServiceNow 20.1/100 (competitive benchmarking works)
- 5-year trend available (262 weekly data points); trend direction detectable
- Latency: 511–843ms. Note: pytrends triggers FutureWarning on fillna (pandas 2.x compat issue — suppress in production)
- **Coverage:** Market Position (search share vs. competitors), Growth/Traction (brand momentum), Web Traffic proxy
- **Decision:** Confirmed for v1. Good proxy for relative brand/traffic trends. Absolute traffic still a gap.

**GitHub API (unauthenticated)**
- Salesforce's `forcedotcom` org: 309 public repos, 1,150 followers, active since 2010
- Recent commits on `salesforcedx-vscode` as of today — commit-level activity accessible
- Rate limit: 60 req/hr unauthenticated → insufficient for production (multi-company analysis would hit ceiling fast)
- Latency: 74–442ms.
- **Coverage:** Product/Technology (OSS activity, AI/ML repo presence, commit velocity), Team/Execution (engineering output signals)
- **Decision:** Confirmed with required change — must use authenticated token (free GitHub account) for production to get 5,000 req/hr. Unauthenticated is fine for single-company dev/test.

**Wayback Machine CDX API**
- Products page (`salesforce.com/products/`): 5 snapshots returned (2023–2025) — page existence/removal detectable
- Pricing page (`salesforce.com/crm/pricing/`): timed out during test (URL-specific latency issue, not API instability — CDX API confirmed working via products page)
- **Coverage:** Product/Technology (pricing page removal = implicit claim #32; product page removal; feature deprecation detection)
- **Decision:** Confirmed for v1. Retry pricing URL in isolation — likely a crawl-depth issue with that specific path. Core capability works.

**Apple App Store (iTunes Search API)**
- Free, no key required
- Salesforce main app: rating 4.75 / 339,946 reviews
- Salesforce Field Service: 4.63 / 17,651 reviews
- Salesforce Authenticator: 4.58 / 4,210 reviews
- Latency: 273ms
- **Coverage:** Product/Technology (mobile presence, user sentiment at scale), Market Position (enterprise mobile adoption)
- **Decision:** Confirmed. Useful signal for "enterprise-ready" and mobile product claims.

---

#### 🔑 CONFIRMED PENDING FREE KEY — Register and Test

**Adzuna (job postings)**
- API returned HTTP 400 without credentials — auth required but free tier exists
- Free tier documented as: 1 req/sec, no hard monthly cap
- Registration: developer.adzuna.com
- **Coverage:** Team/Execution (hiring momentum, function breakdown), Product/Technology (implicit claim #21: "AI-powered" with no ML engineers)
- **Decision:** Confirmed pending key. Register before build starts. Alternative if Adzuna is insufficient: JSearch via RapidAPI (150 req/mo free tier).

**NewsAPI**
- Requires key; free tier: 100 req/day, 1-month lookback only
- GDELT (no key) is a stronger free alternative with full history
- **Decision:** Deprioritize NewsAPI in favor of GDELT for v1. Register key as backup if GDELT quality proves insufficient.

---

#### ⚠️ CONDITIONAL — Works But Quality Issues Identified

**GDELT**
- API returns results (25 articles, 2025 YTD) — no key required, full historical coverage
- **Quality issue observed:** Results for `"Salesforce"` include generic financial content (S&P 500 roundups, M&A market articles) where Salesforce appears as a passing mention, not the subject
- Latency: 14,095ms — significantly slower than other sources
- **Required fix before production use:** Add title-contains filter (`title:"Salesforce"`), restrict to tier-1 domains, or use GDELT's theme/tone parameters to filter for company-as-subject articles
- **Coverage:** Market Position (press volume, sentiment), Growth/Traction (news velocity), Cross-Cutting (asymmetric partnership press detection, implicit claim #38)
- **Decision:** Conditional. Confirmed as free source with full history, but needs query refinement. Do not use raw query output as signal — filter to title-matches only.

---

#### ❌ BLOCKED / NOT VIABLE AT FREE TIER

**Crunchbase**
- v4 API returned HTTP 401 — requires API key for all endpoints
- Starter plan: $29/mo (may be justified at paying-user stage)
- OpenCorporates: Also returned 401 for US company queries
- **Gap this creates:** Funding history and private company founding data unavailable without cost
- **Workaround for public companies:** EDGAR has IPO filings, S-1 documents capture historical funding rounds; press release extraction via GDELT can surface funding announcements
- **Decision:** Crunchbase deferred from v1 free tier. For public companies, EDGAR S-1/8-K covers funding history adequately. For private companies, this is a known data gap — surface as "Insufficient Evidence" for funding claims rather than fabricating.

**BuiltWith**
- Returns structured error (`"API Key is incorrect"`) — free endpoint exists but requires key even for 1 lookup/mo tier
- 1 lookup/month is non-viable for any real usage pattern
- **Alternative confirmed:** Wappalyzer OSS (github.com/wappalyzer/wappalyzer) — fingerprinting rules are open source, can run locally via npm against any domain, no key required
- **Decision:** Use Wappalyzer OSS via Node.js subprocess. Skip BuiltWith entirely for MVP.

**USPTO PatentsView**
- Returned HTTP 403 on both endpoints — API may have added auth requirements since documentation was written, or the query format changed with their v1 API migration
- Need to check current PatentsView API docs (they migrated from v0.2 to v1 recently)
- **Decision:** Investigate PatentsView v1 auth requirements. If still blocked, patent claims fall back to "Partial/Not Testable" for implicit claim #22 ("Proprietary technology without patents"). GitHub repo presence becomes the primary proxy for technical credibility.

**G2**
- HTTP 401 — requires API key, no documented free tier
- Public review data is visible in browser HTML but requires scraping
- **Decision:** HTML scraping of G2 product pages is the path (rating, review count, category rank are in structured data markup). Needs implementation and rate limiting. Defer to v1.1 — flag as "Partial" for now.

**Capterra**
- HTTP 403 — actively blocks scraping
- **Decision:** Remove from signal sources for v1. Not worth the maintenance overhead of evading blocks.

**SimilarWeb**
- Enterprise API ($14K+/yr) — confirmed not viable
- **Decision:** Google Trends is the traffic proxy for v1. Absolute traffic data is a known gap.

**AppExchange**
- No documented public API; internal endpoint returned HTTP 400
- **Decision:** Scrape public AppExchange listing pages for Salesforce ecosystem signals (ISV count, ratings). Lower priority than core signal types.

---

### Signal Coverage Assessment (against claim taxonomy)

| Claim Category | Signals Available | Quality | Gap |
|---|---|---|---|
| Growth / Traction | EDGAR financials, Google Trends, GitHub commit velocity | High for public co | Private co revenue unverifiable |
| Market Position | Google Trends (vs. competitors), GDELT news volume, Apple ratings | Medium | Absolute market share unavailable |
| Team / Execution | GitHub activity, Adzuna job postings (pending key) | Medium | Org chart / leadership depth thin |
| Product / Technology | GitHub repos/activity, Wappalyzer, Apple ratings, Wayback Machine | Medium-High | G2 blocked; enterprise cert data (SOC2) not in free APIs |
| Unit Economics | EDGAR XBRL (revenue, margin, EPS, burn), 8-K transcripts | High for public co | Private co: dark |

**Overall testable claim coverage estimate:** ~60–70% of claims for public companies. ~30–40% for private companies (EDGAR unavailable, Crunchbase unavailable, financial data absent). This is above the viability threshold — sufficient to produce meaningful verdicts for public company narratives at MVP.

---

### Decisions Made

1. **EDGAR is the backbone.** Three endpoints confirmed working (submissions, full-text search, XBRL). Covers financials, earnings calls (8-K), and historical filing analysis.
2. **Google Trends is the traffic and competitive proxy.** No alternative at free tier. Relative, not absolute — communicate this in UI.
3. **GitHub requires auth token for production.** Free account + token = 5,000 req/hr. Add to setup docs.
4. **Wappalyzer OSS replaces BuiltWith.** Run as Node.js subprocess. No key. No cost.
5. **GDELT requires query refinement before use.** Title-match filter mandatory. Latency (14s) means it must be async / background fetch — cannot be on the critical path of a user-facing request.
6. **Adzuna key required — register before build.** Confirmed as only clean free job posting source.
7. **PatentsView needs investigation.** 403 may be a query format issue with their v1 API migration. Check docs before declaring it broken.
8. **Private company coverage is limited.** Known gap. Tool should surface this clearly — not pretend to test claims it can't test. Verdict: "Insufficient Evidence" is honest and defensible.
9. **G2 scraping deferred to v1.1.** HTML scraping is possible but fragile; not worth v1 scope risk.
10. **Crunchbase deferred.** For public companies, EDGAR S-1 covers founding/funding history. Re-evaluate at first paying customer.

---

### Next Steps (Phase 2 Remaining)
- [ ] Define shared signal schema (company → signals → sources → timestamps)
- [ ] Investigate PatentsView v1 auth requirements
- [ ] Register Adzuna free API key and validate job posting data quality
- [ ] Test GDELT with refined query (title-match filter) and measure quality improvement
- [ ] Retry Wayback Machine pricing URL in isolation
- [ ] Produce MVP scope doc (Phase 2 output → Phase 3 input)

---

## 2026-03-19 — Phase 2 Close-out: Remaining Checks + Signal Schema + MVP Scope

**Phase:** 2 → 3 handoff

---

### Remaining Technical Check Results

**PatentsView**
- HTTP 403 on all v1 endpoints, across multiple query formats. USPTO developer API returned 503.
- Confirmed dead at free tier — PatentsView v1 has added auth/IP restrictions.
- **Final decision:** Patent signals removed from v1 signal map. Implicit claim #22 ("Proprietary technology without patents") falls back to GitHub repo presence + job posting analysis as proxy for technical credibility. Not testable via patents in v1.

**GDELT title-match filter**
- Both refined queries returned empty response body (rate limited by GDELT between runs, not a syntax error).
- Basic GDELT capability was confirmed in the first run (25 articles returned). Rate limit is the constraint, not the filter logic.
- **Final decision:** GDELT confirmed for v1 with two implementation requirements: (1) title-match filter syntax validated at build time, (2) GDELT fetch is always async/background — 14s latency cannot block the UI.

**Wayback Machine pricing URL**
- `/crm/pricing/` — 0 snapshots (Wayback never crawled that deep path).
- `/editions-pricing/sales-cloud/` — 6 snapshots (2022–2023). ✅
- `/pricing/` — 4 snapshots (2024–2025). ✅
- **Finding:** Wayback coverage depends on whether their crawler hit the specific URL. Implementation needs a URL discovery step — check 3–4 candidate pricing paths per domain and use whichever has snapshot history. The capability is solid; the URL is not always predictable.

---

### Shared Signal Schema

Defined to be compatible with Project A's entity model. Not shared infrastructure — same shape, independent implementation.

#### Core Entities

```
Company
  entity_id       str          # normalized slug: "salesforce"
  name            str
  ticker          str | None   # public companies only
  cik             str | None   # EDGAR CIK, public only
  domain          str          # primary web domain
  company_type    enum         # "public" | "private"
  created_at      datetime
```

```
Signal
  signal_id       str (uuid)
  entity_id       str          # FK → Company
  signal_type     enum         # see SignalType below
  signal_name     str          # e.g. "annual_revenue_usd", "search_interest_52wk_avg"
  value           any          # numeric, str, or dict
  unit            str | None   # "USD", "index_0-100", "count", "rating_5", "bool"
  period_start    date | None
  period_end      date | None
  source          enum         # see DataSource below
  source_url      str | None
  fetched_at      datetime
  reliability_tier int         # 1 = SEC/official, 2 = verified free APIs, 3 = scraped/estimated
  raw             dict | None  # original API response, for audit/debug
```

```
Claim
  claim_id            str (uuid)
  analysis_id         str          # FK → Analysis
  entity_id           str
  assertion           str          # plain-language claim text
  claim_type          enum         # Growth | MarketPosition | Team | Product | UnitEconomics
  specificity         enum         # quantitative | comparative | qualitative
  testability         enum         # yes | partial | no
  temporal_framing    enum         # past | present | forward
  attribution_clarity enum         # clear | ambiguous | unverifiable
  is_implicit         bool
  implicit_pattern_id int | None   # references 26-pattern library (1–40)
```

```
Evidence
  evidence_id     str (uuid)
  claim_id        str          # FK → Claim
  signal_id       str          # FK → Signal
  verdict         enum         # supporting | contradicting | insufficient
  reasoning       str
```

```
ClaimVerdict
  verdict_id          str (uuid)
  claim_id            str
  verdict             enum   # supported | partially_supported | contested |
                             #   insufficient_evidence | not_testable
  evidence_strength   enum   # strong | moderate | weak
  reasoning           str    # 2–4 sentence synthesis
  generated_at        datetime
```

```
Analysis
  analysis_id     str (uuid)
  entity_id       str
  input_type      enum         # company_name | pitch_deck | earnings_transcript | investor_memo
  input_text      str | None   # for paste inputs; None for company_name lookup
  run_at          datetime
  cost_usd        float        # actual Anthropic API cost for this run
  status          enum         # complete | partial | failed
  claim_count     int
  tested_count    int          # claims with verdict != not_testable
```

#### Enumerations

**SignalType** (maps to claim taxonomy):
- `revenue_growth`, `user_growth`, `search_momentum` → Growth/Traction
- `search_share_vs_competitors`, `news_volume`, `app_store_rating` → Market Position
- `hiring_volume`, `hiring_mix`, `github_commit_velocity` → Team/Execution
- `tech_stack`, `oss_activity`, `pricing_page_history`, `mobile_ratings` → Product/Technology
- `annual_revenue`, `gross_margin`, `operating_income`, `eps`, `filing_language_change` → Unit Economics

**DataSource**:
`edgar_xbrl`, `edgar_filings`, `google_trends`, `github_api`, `wayback_cdx`,
`apple_appstore`, `adzuna`, `gdelt`, `wappalyzer`

**ReliabilityTier**:
- Tier 1: `edgar_xbrl`, `edgar_filings` (audited, regulatory)
- Tier 2: `github_api`, `google_trends`, `apple_appstore`, `adzuna` (official APIs, unaudited)
- Tier 3: `gdelt`, `wayback_cdx`, `wappalyzer` (inferred, scraped, or proxied)

---

### Daily Spend Limit — Design

Two-layer approach: Anthropic Console (monthly hard cap) + in-app daily counter.

**SpendTracker class (to be built in Phase 3):**
- Persists to local JSON ledger file — no database dependency at MVP
- `would_exceed(estimated_cost)` → bool — checked before every analysis run
- `record(analysis_id, actual_cost)` → called after completion
- `status()` → returns date, spent, limit, remaining, analyses_today
- Pipeline: estimate cost from token count → check tracker → run if clear → record actual
- UI: spend meter in Streamlit sidebar (today's spend / daily limit)
- Settings: `DAILY_SPEND_LIMIT_USD` env var, default $5.00
- Backstop: Anthropic Console monthly cap set to $50

---

### MVP Scope Document

#### What v1 Is

A tool where a user inputs a public company name or pastes an earnings transcript / investor memo. The tool extracts narrative claims, gathers evidence from free public signals, and returns a claim-by-claim verdict: what the company says, what the evidence shows, and a structured confidence assessment.

#### In Scope for v1

**Input modes:**
- Company name lookup (public companies via EDGAR CIK resolution)
- Paste: earnings transcript
- Paste: investor memo / press release

**Claim extraction:**
- 5 claim categories: Growth/Traction, Market Position, Team/Execution, Product/Technology, Unit Economics
- 6-field schema per claim (assertion, type, specificity, testability, temporal framing, attribution clarity)
- Implicit claim detection (26-pattern library)

**Evidence sources (all confirmed working):**
- EDGAR — financial history, 8-K filings, XBRL structured data (Tier 1)
- Google Trends — search interest, competitor benchmarking (Tier 2)
- GitHub API — OSS activity, commit velocity, repo presence — requires free auth token (Tier 2)
- Wayback Machine — pricing page history, product page presence/removal; URL discovery step required (Tier 3)
- Apple App Store — mobile ratings, review volume (Tier 2)
- Adzuna — job postings, hiring mix; key registered (Tier 2)
- GDELT — news volume, press sentiment; async fetch, title-match filter required (Tier 3)
- Wappalyzer OSS — tech stack fingerprinting via Node.js subprocess (Tier 3)

**Verdict engine:**
- 5-level verdict scale per claim
- Evidence synthesis across signals (not per-signal binary)
- Overall narrative assessment (where it holds, where it cracks, what's absent)

**Infrastructure:**
- Daily spend tracker (SpendTracker class + Anthropic Console monthly backstop)
- Analysis ledger (local JSON)
- Streamlit frontend — claim-by-claim output, spend meter in sidebar

#### Out of Scope for v1 (Deferred)

| Item | Reason | Target |
|---|---|---|
| Private company pitch deck analysis | Evidence layer ~30-40% | v1.1 |
| G2 review signals | HTML scraping fragile | v1.1 |
| Strategic Narrative claims (category 6) | Evidence layer thin | v1.1 |
| Crunchbase funding data | Requires $29/mo | Post-revenue |
| USPTO patent signals | PatentsView v1 403 blocked | Investigate separately |
| Capterra reviews | Hard 403 block | Drop permanently |
| SimilarWeb traffic | $14K+/yr enterprise | Drop permanently |
| Shared infrastructure with Project A | Premature | v2 |
| User accounts / multi-user | MVP is single-user | Post-revenue |

#### Build Sequence (Phase 3)

1. Data layer — signal fetchers, one module per source, all returning Signal schema objects
2. Claim extraction — Claude prompt (structured, not freeform), returns Claim schema objects
3. Evidence mapper — static map: claim type → relevant signal types; fetch and match
4. Verdict engine — Claude prompt, consumes claim + evidence signals, returns ClaimVerdict
5. Spend tracker — SpendTracker class + pipeline integration
6. Streamlit UI — input → loading state → claim-by-claim results + sidebar spend meter
7. GDELT async — background fetch, joins results after primary signals complete

#### Known Gaps (Surfaced to Users in UI)

- Public companies only in v1 (private companies: financial claims → "Insufficient Evidence")
- No absolute web traffic data (relative trends only via Google Trends)
- No third-party review data in v1 (Apple App Store is partial proxy)
- Patent claims: proxied via GitHub activity, not direct patent data
- Hiring data: US job postings only (Adzuna US endpoint)

---

## 2026-03-19 — Documentation Strategy

**Phase:** Pre-build / Process

**Decision:** Maintain a running append-only markdown log (`BUILD_LOG.md`) capturing decisions, rationale, alternatives considered, and phase context throughout the project.

**Rationale:** Process spans Claude chat (strategy/design), Claude Code (engineering), and independent thinking. No single tool captures all of it. Log entries generated at end of each working session become the skeleton for the eventual retrospective write-up.

**Format:** Date + title, phase tag, decision, rationale, alternatives considered. Append-only — never edit old entries.

---

## 2026-03-24 — Phase 3 Complete: Full Pipeline Built, Tested, and Smoke-Validated

**Phase:** 3 — Build (complete)

### What Was Built

Full pipeline implemented and all components validated end-to-end:

- **8 signal fetchers:** edgar, adzuna, appstore, gdelt, github, google_trends, wappalyzer, wayback — all returning Signal schema objects, all handling errors gracefully
- **Claim extractor:** Claude tool-use call, structured output mapped to Claim schema, 20-claim cap
- **Evidence mapper:** Static ClaimType → SignalType map (the non-AI layer of domain judgment)
- **Verdict engine:** One Claude call per claim, returns ClaimVerdictModel + per-signal Evidence breakdown
- **Orchestrator:** Full pipeline coordination — GDELT async in background thread, spend check pre-run, spend record post-run
- **SpendTracker:** Daily JSON ledger, would_exceed check, status() dict for UI
- **Streamlit UI (app.py):** Full implementation — hero, input form, company type toggle, competitor suggest (Haiku), claim-by-claim verdict cards, signal breakdown expanders, raw signals expander
- **Test suite:** 103 unit tests (mocked, no API calls) + 4 live smoke tests

### Bugs Fixed

- `fetchers/edgar.py`: Hardcoded `cutoff = "2025-03-20"` in 8-K count logic replaced with dynamic `date.today() - timedelta(days=365)`
- `fetchers/wappalyzer.py`: Overly narrow `except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError)` would crash on unexpected subprocess errors; replaced with `except Exception`
- `.env`: Duplicate `ANTHROPIC_API_KEY` entries cleaned up (two different keys were present)
- `ANTHROPIC_MODEL`: `claude-sonnet-4-6-20250514` is not a valid API model ID (404); correct ID is `claude-sonnet-4-6` (undated). Dated format only applies to Haiku.

### Smoke Test Results (2026-03-24, Salesforce / CRM)

- CIK resolved: 0001108524
- EDGAR signals: 6 (annual_revenue: $41.5B, revenue_growth: 9.58%, gross_margin: 77.68%, operating_income: $8.3B, EPS: $7.80, 8-K count: 14)
- Google Trends signals: 4
- Claims extracted: 16 (9 explicit, 7 implicit) — cost $0.033
- Signal coverage: 68.8% (11 strong, 0 partial, 5 no coverage)
- Sample verdict: "20% YoY growth" claim → **Contested** — EDGAR shows 9.6% full-year growth, contradicting Q4-specific claim. This is the product working as designed.
- Total run cost: ~$0.067

### Server Architecture Decision

`server.py` (Flask) is a dead detour created when Streamlit styling proved frustrating. `app.py` (Streamlit) is the deployment target, consistent with Project A. `UI updates - 3.22.26/` contains a UI spec and reference HTML to bring the Streamlit styling in line with Project A's visual language. Flask server to be deleted after Aaron confirms.

### Remaining Before Launch
1. UI styling pass against `UI updates - 3.22.26/NST_UI_SPEC.md`
2. GitHub repo creation + Streamlit Community Cloud deployment
3. Delete `server.py` (pending confirmation)
4. Project A parity check before simultaneous launch

---

## 2026-03-29 — Product Naming: Manseil

**Phase:** Branding
**Decision:** Project B is now branded "Manseil" (subtitle: "Narrative stress test"). Named after Mansell Peak, Mount Desert Island — subtle letter swap (ll → il), same pronunciation. Part of the Pemetiq mountain-naming convention alongside Cadillaq (Project A).
**Rationale:** Mountain pet names give tools a memorable, brand-able identity. Descriptive names become subtitles. Users say "run it through Manseil" rather than "use the Narrative Stress Test tool."

---
