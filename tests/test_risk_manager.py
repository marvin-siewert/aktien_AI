"""
Unit tests for RiskManager (5% position cap, max 3 stocks per sector, max 20% sector weight,
and pre-trade candidate cluster-risk check).
"""

from __future__ import annotations

from src.core.risk_manager import RiskManager
from src.models.entities import PortfolioState, Position, StockMetrics


def test_risk_manager_detects_position_and_sector_violations(sample_portfolio: PortfolioState) -> None:
    """Verify RiskManager computes exact weights and flags >5% position and >20% sector weights."""
    rm = RiskManager(
        max_position_weight_pct=5.0,
        max_sector_weight_pct=20.0,
        max_stocks_per_sector=3,
    )
    report = rm.analyze_portfolio(sample_portfolio, language="de")

    # Total value: MSFT (4000) + SAP (2000) + NVDA (1500) + ALV (2500) = 10000
    assert report.total_value == 10000.0
    assert report.position_weights["MSFT"] == 40.0
    assert report.largest_position_ticker == "MSFT"
    assert report.largest_sector_name == "Technologie & Software"
    assert report.largest_sector_weight_pct == 60.0  # MSFT (40%) + SAP (20%)
    assert len(report.warnings) > 0


def test_sector_stock_count_cap_and_candidate_check() -> None:
    """Verify max 3 stocks per sector rule triggers when a 4th stock in the same sector is evaluated."""
    portfolio = PortfolioState(
        portfolio_name="Tech Heavy",
        positions=[
            Position(ticker="MSFT", quantity=10, current_price=100, sector="Technologie & Software", country="USA"),
            Position(ticker="SAP.DE", quantity=10, current_price=100, sector="Technologie & Software", country="Deutschland"),
            Position(ticker="ORCL", quantity=10, current_price=100, sector="Technologie & Software", country="USA"),
            Position(ticker="ALV.DE", quantity=170, current_price=100, sector="Finanzen & Versicherungen", country="Deutschland"),
        ],
    )
    rm = RiskManager(max_stocks_per_sector=3, max_sector_weight_pct=20.0)

    candidate_same_sector = StockMetrics(
        ticker="CRM",
        name="Salesforce Inc.",
        current_price=280.0,
        target_mean_price=350.0,
        upside_pct=25.0,
        recommendation_key="buy",
        number_of_analyst_opinions=35,
        assigned_sector="Technologie & Software",
        assigned_country="USA",
    )
    warning = rm.check_candidate_cluster_risk(candidate_same_sector, portfolio, language="de")
    assert "3/3" in warning

    candidate_new_sector = StockMetrics(
        ticker="LLY",
        name="Eli Lilly",
        current_price=795.0,
        target_mean_price=1000.0,
        upside_pct=25.8,
        recommendation_key="strong_buy",
        number_of_analyst_opinions=28,
        assigned_sector="Gesundheit & Pharma",
        assigned_country="USA",
    )
    assert rm.check_candidate_cluster_risk(candidate_new_sector, portfolio, language="de") == ""
