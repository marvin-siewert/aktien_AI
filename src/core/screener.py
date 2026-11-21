"""
Monthly Deep Dive Screener & Unbiased Portfolio Re-Evaluator.

Combines:
1. Sunk-cost-free re-evaluation of existing portfolio holdings (ignoring historical buy-in prices).
2. Quantitative analyst screening of the selected universe (Quick-Scan or Full-Scan):
   - Analyst consensus in ('buy', 'strong_buy', 'outperform')
   - Minimum number of analysts >= 12 (configurable)
   - Target price upside >= 20.0% (configurable)
3. Anti-cluster-risk annotation via RiskManager.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from src.core.risk_manager import RiskManager
from src.models.entities import PortfolioState, StockMetrics
from src.services.market_data import MarketDataService


ALLOWED_BUY_RECOMMENDATIONS = {"buy", "strong_buy", "strongbuy", "outperform"}


@dataclass
class DeepDiveScreeningResult:
    """Holds both the unbiased re-evaluation of current holdings and the top new buy candidates."""

    holdings_metrics: List[StockMetrics]
    buy_candidates: List[StockMetrics]
    universe_metrics: List[StockMetrics]


class StockScreener:
    """
    Executes the quantitative Monthly Deep Dive screening and portfolio re-evaluation.
    """

    def __init__(
        self,
        market_data: Optional[MarketDataService] = None,
        risk_manager: Optional[RiskManager] = None,
    ) -> None:
        self.market_data = market_data or MarketDataService()
        self.risk_manager = risk_manager or RiskManager()

    def passes_filter(
        self,
        metrics: StockMetrics,
        min_analysts: int = 12,
        min_upside_pct: float = 20.0,
        allowed_recommendations: Optional[set[str]] = None,
    ) -> bool:
        """
        Evaluate whether a stock satisfies all quantitative Monthly Deep Dive criteria.
        """
        allowed = allowed_recommendations or ALLOWED_BUY_RECOMMENDATIONS
        rec_ok = metrics.recommendation_key.strip().lower() in allowed
        analysts_ok = metrics.number_of_analyst_opinions >= min_analysts
        upside_ok = metrics.upside_pct >= min_upside_pct
        return bool(rec_ok and analysts_ok and upside_ok)

    def run_deep_dive_scan(
        self,
        portfolio: PortfolioState,
        scan_mode: str = "quick",
        min_analysts: int = 12,
        min_upside_pct: float = 20.0,
        max_candidates: int = 250,
        use_cache: bool = True,
        language: str = "de",
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> DeepDiveScreeningResult:
        """
        1. Re-evaluates all existing portfolio holdings without buy-in price anchoring.
        2. Scans the chosen universe ('quick' or 'full') for undervalued buy candidates.
        3. Annotates candidates with cluster-risk warnings against the existing portfolio.
        """
        holding_tickers = {pos.ticker.strip().upper() for pos in portfolio.positions if pos.ticker.strip()}
        universe_tickers = self.market_data.get_universe_tickers(mode=scan_mode, include_custom=True)

        # Ensure all current portfolio holdings are included in the scan batch
        all_tickers: List[str] = list(holding_tickers) + [
            t for t in universe_tickers if t not in holding_tickers
        ]

        all_metrics = self.market_data.fetch_batch_metrics(
            tickers=all_tickers,
            holding_tickers=holding_tickers,
            use_cache=use_cache,
            progress_callback=progress_callback,
        )

        holdings_metrics: List[StockMetrics] = []
        buy_candidates: List[StockMetrics] = []

        for item in all_metrics:
            item.passes_quantitative_filter = self.passes_filter(
                item,
                min_analysts=min_analysts,
                min_upside_pct=min_upside_pct,
            )
            if item.is_holding:
                holdings_metrics.append(item)
            elif item.passes_quantitative_filter:
                item.cluster_risk_warning = self.risk_manager.check_candidate_cluster_risk(
                    candidate=item,
                    portfolio=portfolio,
                    language=language,
                )
                buy_candidates.append(item)

        # Sort holdings by upside ascending (so holdings near/above target that need reallocation stand out)
        holdings_metrics.sort(key=lambda m: m.upside_pct)

        # Sort new buy candidates: compliant sectors first, then highest upside_pct descending
        buy_candidates.sort(
            key=lambda m: (bool(m.cluster_risk_warning), -m.upside_pct, -m.number_of_analyst_opinions)
        )

        return DeepDiveScreeningResult(
            holdings_metrics=holdings_metrics,
            buy_candidates=buy_candidates[:max_candidates],
            universe_metrics=all_metrics,
        )
