"""
Unit tests for StockScreener quantitative filters (buy/strong_buy consensus,
analyst count >= 12, target price upside >= 20%).
"""

from __future__ import annotations

from src.core.screener import StockScreener
from src.models.entities import StockMetrics
from src.services.market_data import MarketDataService
from src.storage.json_store import JsonStore
from src.ui.charts import build_stock_price_history_chart
from src.ui.theme_manager import get_theme


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
