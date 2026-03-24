from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from schema.enums import (
    AnalysisStatus,
    AttributionClarity,
    ClaimType,
    ClaimVerdict,
    CompanyType,
    DataSource,
    EvidenceStrength,
    EvidenceVerdict,
    InputType,
    SignalType,
    Specificity,
    TemporalFraming,
    Testability,
)


def _uuid() -> str:
    return str(uuid.uuid4())


class Company(BaseModel):
    entity_id: str  # normalized slug, e.g. "salesforce"
    name: str
    ticker: str | None = None
    cik: str | None = None  # EDGAR CIK for public companies
    domain: str  # primary web domain, e.g. "salesforce.com"
    company_type: CompanyType
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Signal(BaseModel):
    signal_id: str = Field(default_factory=_uuid)
    entity_id: str
    signal_type: SignalType
    signal_name: str
    value: Any
    unit: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    source: DataSource
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    reliability_tier: int  # 1, 2, or 3
    raw: dict | None = None


class Claim(BaseModel):
    claim_id: str = Field(default_factory=_uuid)
    analysis_id: str
    entity_id: str
    assertion: str
    claim_type: ClaimType
    specificity: Specificity
    testability: Testability
    temporal_framing: TemporalFraming
    attribution_clarity: AttributionClarity
    is_implicit: bool = False
    implicit_pattern_id: int | None = None  # 1–40 per 26-pattern library


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=_uuid)
    claim_id: str
    signal_id: str
    verdict: EvidenceVerdict
    reasoning: str


class ClaimVerdictModel(BaseModel):
    """Structured verdict for a single claim."""
    verdict_id: str = Field(default_factory=_uuid)
    claim_id: str
    verdict: ClaimVerdict
    evidence_strength: EvidenceStrength
    reasoning: str  # 2–4 sentence synthesis
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class Analysis(BaseModel):
    analysis_id: str = Field(default_factory=_uuid)
    entity_id: str
    input_type: InputType
    input_text: str | None = None
    run_at: datetime = Field(default_factory=datetime.utcnow)
    cost_usd: float = 0.0
    status: AnalysisStatus = AnalysisStatus.partial
    claim_count: int = 0
    tested_count: int = 0  # claims with verdict != not_testable
