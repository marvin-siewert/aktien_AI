"""Compatibility re-export for `src.screener`."""

from src.core.screener import ALLOWED_BUY_RECOMMENDATIONS, DeepDiveScreeningResult, StockScreener

__all__ = ["StockScreener", "DeepDiveScreeningResult", "ALLOWED_BUY_RECOMMENDATIONS"]
