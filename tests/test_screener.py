"""
Unit tests for StockScreener quantitative filters (buy/strong_buy consensus,
analyst count >= 12, target price upside >= 20%).
"""

from __future__ import annotations

from src.core.screener import StockScreener
from src.models.entities import PortfolioState, Position, StockMetrics
from src.services.market_data import MarketDataService
from src.storage.json_store import JsonStore
from src.ui.charts import build_portfolio_target_price_chart, build_stock_price_history_chart
from src.ui.theme_manager import get_theme


def test_holding_enrichment_with_buy_in_and_target_chart(temp_store: JsonStore) -> None:
    """Verify buy-in price, live FX conversion (USD -> EUR), gain/loss, and 3-bar target price chart."""
    # Seed deterministic FX rate USD -> EUR = 0.90 in cache
    temp_store.set_cache("fx_USD_EUR", 0.90)
    mds = MarketDataService(store=temp_store)
    screener = StockScreener(market_data=mds)
    portfolio = PortfolioState(
        portfolio_name="Scalable Live",
        positions=[
            Position(
                ticker="NVDA",
                name="NVIDIA",
                quantity=2.0,
                buy_in_price=120.00,
                current_price=135.00,
                currency="EUR",
            )
        ],
    )
    metrics = StockMetrics(
        ticker="NVDA",
        name="NVIDIA Corp.",
        current_price=150.0,
        target_mean_price=180.0,
        upside_pct=20.0,
        currency="USD",
        is_holding=True,
    )
    enriched = screener.enrich_holding_metrics_with_position(metrics, portfolio)
    assert enriched.currency == "EUR"
    assert enriched.buy_in_price == 120.00
    assert enriched.current_price == 135.00  # 150.0 USD * 0.90
    assert enriched.target_mean_price == 162.00  # 180.0 USD * 0.90
    assert enriched.gain_loss_abs == 30.00  # (135 - 120) * 2
    assert enriched.gain_loss_pct == 12.50

    fig = build_portfolio_target_price_chart([enriched], get_theme("clean_blue"))
    # Must contain 3 bar traces: Kaufpreis, Aktueller Kurs, Analysten-Kursziel
    assert len(fig.data) == 3


def test_price_history_and_chart_builder(temp_store: JsonStore) -> None:
    """Verify historical stock price series retrieval and interactive Plotly chart generation."""
    mds = MarketDataService(store=temp_store)
    hist_df = mds.fetch_price_history("MSFT", period="1y", use_cache=True)
    assert not hist_df.empty
    assert "Date" in hist_df.columns
    assert "Close" in hist_df.columns

    fig = build_stock_price_history_chart(
        history_df=hist_df,
        ticker="MSFT",
        company_name="Microsoft Corp.",
        currency="USD",
        target_price=515.0,
        theme=get_theme("clean_blue"),
        period_label="1Y",
    )
    assert len(fig.data) >= 1


def test_screener_passes_valid_candidate(sample_candidate_metrics: StockMetrics) -> None:
    """Verify a candidate with strong_buy, 34 analysts, and 33.3% upside passes the filter."""
    screener = StockScreener()
    assert screener.passes_filter(
        sample_candidate_metrics,
        min_analysts=12,
        min_upside_pct=20.0,
    ) is True


def test_screener_rejects_low_analyst_count(sample_candidate_metrics: StockMetrics) -> None:
    """Verify stocks with fewer than min_analysts (12) are rejected."""
    screener = StockScreener()
    low_coverage = sample_candidate_metrics.model_copy(update={"number_of_analyst_opinions": 8})
    assert screener.passes_filter(low_coverage, min_analysts=12, min_upside_pct=20.0) is False


def test_screener_rejects_low_upside_or_hold_consensus(sample_candidate_metrics: StockMetrics) -> None:
    """Verify stocks with <20% upside or 'hold'/'sell' recommendation are rejected."""
    screener = StockScreener()

    low_upside = sample_candidate_metrics.model_copy(update={"upside_pct": 14.5})
    assert screener.passes_filter(low_upside, min_analysts=12, min_upside_pct=20.0) is False

    hold_rating = sample_candidate_metrics.model_copy(update={"recommendation_key": "hold"})
    assert screener.passes_filter(hold_rating, min_analysts=12, min_upside_pct=20.0) is False
