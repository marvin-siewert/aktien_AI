"""
Shared pytest fixtures for the Stock Analysis & Portfolio Monitoring test suite.

Provides isolated temporary directories (`tmp_path`) so tests never overwrite
the user's live data in `data/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from src.core.taxonomy_manager import TaxonomyManager
from src.models.entities import NewsArticle, PortfolioState, Position, StockMetrics
from src.storage.json_store import JsonStore


@pytest.fixture
def temp_store(tmp_path: Path) -> JsonStore:
    """Provide an isolated JsonStore backed by a temporary directory."""
    data_dir = tmp_path / "test_data"
    return JsonStore(data_dir=data_dir)


@pytest.fixture
def temp_taxonomy(temp_store: JsonStore) -> TaxonomyManager:
    """Provide a TaxonomyManager initialized with default sectors and countries in temp_store."""
    return TaxonomyManager(store=temp_store)


@pytest.fixture
def sample_portfolio() -> PortfolioState:
    """Provide a deterministic multi-sector, multi-country portfolio for testing."""
    return PortfolioState(
        portfolio_name="Test Depot",
        source="manual",
        positions=[
            Position(
                ticker="MSFT",
                name="Microsoft Corp.",
                quantity=10.0,
                buy_in_price=300.0,
                current_price=400.0,
                currency="USD",
                sector="Technologie & Software",
                country="USA",
            ),
            Position(
                ticker="SAP.DE",
                name="SAP SE",
                quantity=10.0,
                buy_in_price=150.0,
                current_price=200.0,
                currency="EUR",
                sector="Technologie & Software",
                country="Deutschland",
            ),
            Position(
                ticker="NVDA",
                name="NVIDIA Corp.",
                quantity=10.0,
                buy_in_price=100.0,
                current_price=150.0,
                currency="USD",
                sector="Halbleiter & Hardware",
                country="USA",
            ),
            Position(
                ticker="ALV.DE",
                name="Allianz SE",
                quantity=10.0,
                buy_in_price=220.0,
                current_price=250.0,
                currency="EUR",
                sector="Finanzen & Versicherungen",
                country="Deutschland",
            ),
        ],
    )


@pytest.fixture
def sample_news_articles() -> List[NewsArticle]:
    """Provide sample news articles with verified URLs for AI anti-hallucination tests."""
    return [
        NewsArticle(
            title="ASML reports strong EUV bookings for next-gen nodes",
            url="https://www.reuters.com/technology/asml-euv-orders-2026",
            source="Reuters",
            published_at="2026-11-20",
            snippet="Chip equipment maker ASML saw strong bookings driven by AI wafer demand.",
        ),
        NewsArticle(
            title="Semiconductor capex outlook remains robust for 2027",
            url="https://finance.yahoo.com/news/semiconductor-capex-2027",
            source="Yahoo Finance",
            published_at="2026-11-19",
            snippet="Foundries expand 2nm capacity across US and Europe.",
        ),
    ]


@pytest.fixture
def sample_candidate_metrics() -> StockMetrics:
    """Provide a sample undervalued stock candidate passing quantitative filters."""
    return StockMetrics(
        ticker="ASML.AS",
        name="ASML Holding N.V.",
        current_price=645.0,
        previous_close=680.0,
        daily_change_pct=-5.15,
        target_mean_price=860.0,
        upside_pct=33.33,
        recommendation_key="strong_buy",
        number_of_analyst_opinions=34,
        market_cap=258000000000,
        currency="EUR",
        raw_sector="Technology",
        raw_industry="Semiconductor Equipment & Materials",
        raw_country="Netherlands",
        assigned_sector="Halbleiter & Hardware",
        assigned_country="Niederlande",
        is_holding=False,
    )
