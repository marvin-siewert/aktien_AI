"""Compatibility re-export for `src.broker_scalable`."""

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
