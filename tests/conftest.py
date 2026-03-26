"""
Shared fixtures for Project B test suite.
"""
from __future__ import annotations

from datetime import date

import pytest

from schema.enums import (
    AttributionClarity,
    ClaimType,
    CompanyType,
    DataSource,
    EvidenceStrength,
    EvidenceVerdict,
    ClaimVerdict,
    SignalType,
    Specificity,
    TemporalFraming,
    Testability,
)
from schema.models import Claim, ClaimVerdictModel, Company, Evidence, Signal


@pytest.fixture
def salesforce() -> Company:
    return Company(
        entity_id="salesforce",
        name="Salesforce",
        ticker="CRM",
        cik="0001108524",
        domain="salesforce.com",
        company_type=CompanyType.public,
    )


@pytest.fixture
def private_company() -> Company:
    return Company(
        entity_id="acmecorp",
        name="Acme Corp",
        domain="acme.io",
        company_type=CompanyType.private,
    )


@pytest.fixture
def growth_claim() -> Claim:
    return Claim(
        analysis_id="test-001",
        entity_id="salesforce",
        assertion="Salesforce delivered 20% year-over-year revenue growth",
        claim_type=ClaimType.growth,
        specificity=Specificity.quantitative,
        testability=Testability.yes,
        temporal_framing=TemporalFraming.past,
        attribution_clarity=AttributionClarity.clear,
    )


@pytest.fixture
def product_claim() -> Claim:
    return Claim(
        analysis_id="test-001",
        entity_id="salesforce",
        assertion="Our AI platform uses proprietary large language models",
        claim_type=ClaimType.product,
        specificity=Specificity.qualitative,
        testability=Testability.partial,
        temporal_framing=TemporalFraming.present,
        attribution_clarity=AttributionClarity.ambiguous,
    )


@pytest.fixture
def not_testable_claim() -> Claim:
    return Claim(
        analysis_id="test-001",
        entity_id="salesforce",
        assertion="We have the best culture in the industry",
        claim_type=ClaimType.team,
        specificity=Specificity.qualitative,
        testability=Testability.no,
        temporal_framing=TemporalFraming.present,
        attribution_clarity=AttributionClarity.unverifiable,
    )


@pytest.fixture
def revenue_signal(salesforce: Company) -> Signal:
    return Signal(
        entity_id=salesforce.entity_id,
        signal_type=SignalType.revenue_growth,
        signal_name="revenue_growth_yoy_pct",
        value=20.5,
        unit="pct",
        period_start=date(2024, 1, 31),
        period_end=date(2025, 1, 31),
        source=DataSource.edgar_xbrl,
        reliability_tier=1,
    )


@pytest.fixture
def tech_stack_signal(salesforce: Company) -> Signal:
    return Signal(
        entity_id=salesforce.entity_id,
        signal_type=SignalType.tech_stack,
        signal_name="detected_technologies",
        value={"React": True, "AWS": True, "Heroku": True},
        source=DataSource.wappalyzer,
        reliability_tier=3,
    )


@pytest.fixture
def sample_verdict(growth_claim: Claim) -> ClaimVerdictModel:
    return ClaimVerdictModel(
        claim_id=growth_claim.claim_id,
        verdict=ClaimVerdict.supported,
        evidence_strength=EvidenceStrength.strong,
        reasoning="EDGAR XBRL data confirms 20.5% YoY revenue growth.",
    )
