from enum import Enum


class ClaimType(str, Enum):
    growth = "growth"
    market_position = "market_position"
    team = "team"
    product = "product"
    unit_economics = "unit_economics"


class SignalType(str, Enum):
    # Growth / Traction
    revenue_growth = "revenue_growth"
    user_growth = "user_growth"
    search_momentum = "search_momentum"
    # Market Position
    search_share_vs_competitors = "search_share_vs_competitors"
    news_volume = "news_volume"
    app_store_rating = "app_store_rating"
    # Team / Execution
    hiring_volume = "hiring_volume"
    hiring_mix = "hiring_mix"
    github_commit_velocity = "github_commit_velocity"
    # Product / Technology
    tech_stack = "tech_stack"
    oss_activity = "oss_activity"
    pricing_page_history = "pricing_page_history"
    mobile_ratings = "mobile_ratings"
    # Unit Economics
    annual_revenue = "annual_revenue"
    gross_margin = "gross_margin"
    operating_income = "operating_income"
    eps = "eps"
    filing_language_change = "filing_language_change"


class DataSource(str, Enum):
    edgar_xbrl = "edgar_xbrl"
    edgar_filings = "edgar_filings"
    google_trends = "google_trends"
    github_api = "github_api"
    wayback_cdx = "wayback_cdx"
    apple_appstore = "apple_appstore"
    adzuna = "adzuna"
    gdelt = "gdelt"
    wappalyzer = "wappalyzer"


class CompanyType(str, Enum):
    public = "public"
    private = "private"


class InputType(str, Enum):
    company_name = "company_name"
    pitch_deck = "pitch_deck"
    earnings_transcript = "earnings_transcript"
    investor_memo = "investor_memo"


class Specificity(str, Enum):
    quantitative = "quantitative"
    comparative = "comparative"
    qualitative = "qualitative"


class Testability(str, Enum):
    yes = "yes"
    partial = "partial"
    no = "no"


class TemporalFraming(str, Enum):
    past = "past"
    present = "present"
    forward = "forward"


class AttributionClarity(str, Enum):
    clear = "clear"
    ambiguous = "ambiguous"
    unverifiable = "unverifiable"


class EvidenceVerdict(str, Enum):
    supporting = "supporting"
    contradicting = "contradicting"
    insufficient = "insufficient"


class ClaimVerdict(str, Enum):
    supported = "supported"
    partially_supported = "partially_supported"
    contested = "contested"
    insufficient_evidence = "insufficient_evidence"
    not_testable = "not_testable"


class EvidenceStrength(str, Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"


class AnalysisStatus(str, Enum):
    complete = "complete"
    partial = "partial"
    failed = "failed"
