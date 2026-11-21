"""
Backward-compatible Scalable Capital Broker module alias.
Re-exports ScalableCliAdapter, BankCsvImportAdapter, and DemoPortfolioAdapter.
"""

from src.services.broker_adapters import (
    BankCsvImportAdapter,
    DemoPortfolioAdapter,
    ScalableCliAdapter,
    parse_localized_float,
)

__all__ = [
    "ScalableCliAdapter",
    "BankCsvImportAdapter",
    "DemoPortfolioAdapter",
    "parse_localized_float",
]
