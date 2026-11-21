"""
Daily Sentinel Engine ('Täglicher Kurssprung-Wächter').

Monitors ONLY current portfolio positions for unusual daily moves (default: > +5% or < -5%).
Only when a position exceeds the threshold does it fetch 24-hour news, load the stored
buy thesis from `data/portfolio_thesis.json`, and verify via LLM whether the thesis is:
- CONFIRMED (catalyst materialized)
- BROKEN (fundamental premise invalidated -> sell signal)
- UNTOUCHED (market noise)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.models.entities import PortfolioState, SentinelAlert, ThesisRecord
from src.services.ai_analyzer import AIAnalyzer
from src.services.market_data import MarketDataService
from src.services.news_fetcher import NewsFetcher
from src.storage.json_store import JsonStore


class SentinelEngine:
    """
    Core engine for the Daily Sentinel check, shared between the standalone CLI (`daily_sentinel.py`)
    and the interactive Streamlit dashboard tab.
    """

    def __init__(
        self,
        store: Optional[JsonStore] = None,
        market_data: Optional[MarketDataService] = None,
        news_fetcher: Optional[NewsFetcher] = None,
        ai_analyzer: Optional[AIAnalyzer] = None,
    ) -> None:
        self.store = store or JsonStore()
        self.market_data = market_data or MarketDataService(self.store)
        self.news_fetcher = news_fetcher or NewsFetcher()
        self.ai_analyzer = ai_analyzer or AIAnalyzer()

    def run_sentinel_check(
        self,
        portfolio: PortfolioState,
        threshold_pct: float = 5.0,
        use_cache: bool = False,
        language: str = "de",
    ) -> List[SentinelAlert]:
        """
        Check all positions in `portfolio` against `threshold_pct`.
        Returns a list of `SentinelAlert` objects (triggered alerts first, sorted by absolute move).
        """
        saved_theses_raw: Dict[str, Dict] = self.store.load_theses()
        alerts: List[SentinelAlert] = []
        is_de = language.lower().startswith("de")

        for pos in portfolio.positions:
            ticker = pos.ticker.strip().upper()
            if not ticker or pos.quantity <= 0:
                continue

            metrics = self.market_data.fetch_stock_metrics(ticker, use_cache=use_cache, is_holding=True)
            current_price = metrics.current_price if metrics.current_price > 0 else pos.current_price
            prev_close = metrics.previous_close if metrics.previous_close > 0 else current_price
            daily_change = metrics.daily_change_pct

            triggered = abs(daily_change) >= abs(threshold_pct)
            raw_thesis = saved_theses_raw.get(ticker)
            thesis_obj: Optional[ThesisRecord] = None
            if isinstance(raw_thesis, dict):
                try:
                    thesis_obj = ThesisRecord(**raw_thesis)
                except Exception:
                    thesis_obj = None

            if not triggered:
                alerts.append(
                    SentinelAlert(
                        ticker=ticker,
                        company_name=metrics.name or pos.name or ticker,
                        quantity=pos.quantity,
                        current_price=current_price,
                        previous_close=prev_close,
                        daily_change_pct=daily_change,
                        triggered=False,
                        has_saved_thesis=thesis_obj is not None,
                        status="NORMAL",
                        reasoning=(
                            f"Normale Tagesbewegung ({daily_change:+.2f}% liegt innerhalb der ±{threshold_pct:.1f}%-Schwelle)."
                            if is_de
                            else f"Normal daily fluctuation ({daily_change:+.2f}% is within ±{threshold_pct:.1f}% threshold)."
                        ),
                        action_recommendation="Kein Eingriff nötig." if is_de else "No action required.",
                        cited_urls=[],
                    )
                )
                continue

            # Triggered! Fetch 24-hour news and run LLM thesis verification
            articles_24h = self.news_fetcher.fetch_news(
                ticker=ticker,
                company_name=metrics.name or pos.name,
                days=1,
                max_results=5,
            )
            llm_eval = self.ai_analyzer.evaluate_sentinel_move(
                ticker=ticker,
                company_name=metrics.name or pos.name or ticker,
                daily_change_pct=daily_change,
                thesis=thesis_obj,
                articles_24h=articles_24h,
                language=language,
            )

            alerts.append(
                SentinelAlert(
                    ticker=ticker,
                    company_name=metrics.name or pos.name or ticker,
                    quantity=pos.quantity,
                    current_price=current_price,
                    previous_close=prev_close,
                    daily_change_pct=daily_change,
                    triggered=True,
                    has_saved_thesis=thesis_obj is not None,
                    status=llm_eval.status,
                    reasoning=llm_eval.reasoning,
                    action_recommendation=llm_eval.action_recommendation,
                    cited_urls=llm_eval.cited_urls,
                )
            )

        # Sort triggered positions to the top, ordered by largest absolute percentage move
        alerts.sort(key=lambda a: (not a.triggered, -abs(a.daily_change_pct)))
        return alerts
