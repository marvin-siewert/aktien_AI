"""
Unit tests for the Daily Sentinel Engine (`src/core/sentinel_engine.py`).

Verifies:
- Holdings with normal daily movement (< 5%) are NOT triggered and do not call the news/LLM pipeline.
- Holdings with unusual daily jumps (>= +/- 5%) trigger 24h news retrieval and thesis evaluation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.sentinel_engine import SentinelEngine
from src.models.entities import (
    NewsArticle,
    PortfolioState,
    Position,
    SentinelLLMOutput,
    StockMetrics,
)
from src.storage.json_store import JsonStore


def test_sentinel_triggers_only_above_threshold(temp_store: JsonStore) -> None:
    """Verify Sentinel only fetches 24h news and runs AI check for stocks exceeding +/-5% move."""
    portfolio = PortfolioState(
        portfolio_name="Sentinel Test",
        positions=[
            Position(ticker="MSFT", name="Microsoft", quantity=10, current_price=425.0),
            Position(ticker="ASML.AS", name="ASML", quantity=5, current_price=645.0),
        ],
    )

    # Save a thesis for ASML.AS
    temp_store.save_thesis(
        "ASML.AS",
        {
            "ticker": "ASML.AS",
            "company_name": "ASML Holding N.V.",
            "entry_price": 660.0,
            "target_price": 860.0,
            "thesis_summary": "EUV monopoly intact.",
            "catalysts": ["2nm TSMC orders"],
            "risks": ["Export restrictions"],
            "source_urls": ["https://www.asml.com"],
        },
    )

    mock_market = MagicMock()
    # MSFT moved +1.2% (below 5% threshold), ASML.AS moved -6.5% (above 5% threshold)
    mock_market.fetch_stock_metrics.side_effect = lambda ticker, **kwargs: (
        StockMetrics(
            ticker="MSFT",
            name="Microsoft",
            current_price=425.0,
            previous_close=420.0,
            daily_change_pct=1.19,
        )
        if ticker == "MSFT"
        else StockMetrics(
            ticker="ASML.AS",
            name="ASML Holding N.V.",
            current_price=645.0,
            previous_close=690.0,
            daily_change_pct=-6.52,
        )
    )

    mock_news = MagicMock()
    mock_news.fetch_news.return_value = [
        NewsArticle(
            title="ASML drops on sector rotation",
            url="https://www.reuters.com/asml-24h",
            source="Reuters",
        )
    ]

    mock_ai = MagicMock()
    mock_ai.evaluate_sentinel_move.return_value = SentinelLLMOutput(
        status="UNTOUCHED",
        reasoning="Sector-wide rotation without fundamental change to EUV demand.",
        action_recommendation="Hold position.",
        cited_urls=["https://www.reuters.com/asml-24h"],
    )

    engine = SentinelEngine(
        store=temp_store,
        market_data=mock_market,
        news_fetcher=mock_news,
        ai_analyzer=mock_ai,
    )

    alerts = engine.run_sentinel_check(portfolio=portfolio, threshold_pct=5.0)
    assert len(alerts) == 2

    # Triggered alert (ASML.AS) is sorted first
    asml_alert = alerts[0]
    msft_alert = alerts[1]

    assert asml_alert.ticker == "ASML.AS"
    assert asml_alert.triggered is True
    assert asml_alert.status == "UNTOUCHED"
    assert asml_alert.cited_urls == ["https://www.reuters.com/asml-24h"]

    assert msft_alert.ticker == "MSFT"
    assert msft_alert.triggered is False
    assert msft_alert.status == "NORMAL"

    # NewsFetcher and AIAnalyzer must have been called ONLY once (for ASML.AS, not for MSFT)
    assert mock_news.fetch_news.call_count == 1
    assert mock_ai.evaluate_sentinel_move.call_count == 1
