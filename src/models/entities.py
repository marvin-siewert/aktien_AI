"""
Domain models and structured output schemas for the Stock Analysis & Portfolio System.

This module strictly separates data structures from business logic and GUI components.
It uses Pydantic models for validated persistence and LLM Structured Outputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Position(BaseModel):
    """Represents a single stock position in a portfolio."""

    ticker: str = Field(..., description="Yahoo Finance ticker symbol, e.g. 'AAPL' or 'SAP.DE'")
    name: str = Field(default="", description="Full company name")
    isin: str = Field(default="", description="Optional ISIN identifier")
    quantity: float = Field(..., ge=0.0, description="Number of shares held")
    buy_in_price: float = Field(default=0.0, ge=0.0, description="Historical buy-in price per share")
    current_price: float = Field(default=0.0, ge=0.0, description="Latest market price per share")
    currency: str = Field(default="EUR", description="Trading currency code")
    sector: str = Field(default="Sonstige / Unklassifiziert", description="Assigned sector category")
    country: str = Field(default="Sonstige / Global", description="Assigned country category")

    @property
    def market_value(self) -> float:
        """Calculate current total market value of this holding."""
        price = self.current_price if self.current_price > 0 else self.buy_in_price
        return round(self.quantity * price, 2)

    @property
    def cost_basis(self) -> float:
        """Calculate total historical cost basis of this holding."""
        return round(self.quantity * self.buy_in_price, 2)

    @property
    def gain_loss_abs(self) -> float:
        """Calculate absolute unrealized profit/loss."""
        if self.buy_in_price <= 0:
            return 0.0
        return round(self.market_value - self.cost_basis, 2)

    @property
    def gain_loss_pct(self) -> float:
        """Calculate percentage unrealized profit/loss."""
        if self.cost_basis <= 0:
            return 0.0
        return round(((self.market_value - self.cost_basis) / self.cost_basis) * 100.0, 2)


class PortfolioState(BaseModel):
    """Represents a complete portfolio state that can be saved, loaded, or imported."""

    portfolio_name: str = Field(default="Mein Hauptdepot", description="Human-readable portfolio name")
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"),
        description="ISO timestamp of last modification",
    )
    source: str = Field(
        default="manual",
        description="Origin of the portfolio state ('manual', 'scalable_cli', 'csv_import', 'demo')",
    )
    positions: List[Position] = Field(default_factory=list, description="List of portfolio holdings")

    @property
    def total_market_value(self) -> float:
        """Calculate sum of market values across all positions."""
        return round(sum(pos.market_value for pos in self.positions), 2)

    @property
    def total_cost_basis(self) -> float:
        """Calculate sum of historical buy-in cost basis across all positions."""
        return round(sum(pos.cost_basis for pos in self.positions), 2)

    @property
    def total_gain_loss_abs(self) -> float:
        """Calculate total unrealized gain/loss across all positions with a valid buy-in price."""
        return round(sum(pos.gain_loss_abs for pos in self.positions), 2)

    @property
    def total_gain_loss_pct(self) -> float:
        """Calculate percentage unrealized gain/loss across the entire portfolio."""
        cost = sum(pos.cost_basis for pos in self.positions if pos.buy_in_price > 0)
        val = sum(pos.market_value for pos in self.positions if pos.buy_in_price > 0)
        if cost <= 0:
            return 0.0
        return round(((val - cost) / cost) * 100.0, 2)


class TaxonomyConfig(BaseModel):
    """Configuration for customizable sector and country lists, mappings, and ticker overrides."""

    version_label: str = Field(default="Standard", description="Name or comment for this taxonomy version")
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"),
        description="ISO timestamp when this taxonomy was saved",
    )
    sectors: List[str] = Field(default_factory=list, description="List of available sectors/industries")
    countries: List[str] = Field(default_factory=list, description="List of available countries/regions")
    sector_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Lowercase keyword mapping from raw yfinance sector/industry to user sector",
    )
    country_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Lowercase keyword mapping from raw yfinance country to user country",
    )
    ticker_overrides: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Manual per-ticker overrides: {'TICKER': {'sector': '...', 'country': '...'}}",
    )


class StockMetrics(BaseModel):
    """Market data and analyst consensus metrics for a single stock ticker."""

    ticker: str
    name: str = ""
    current_price: float = 0.0
    previous_close: float = 0.0
    daily_change_pct: float = 0.0
    target_mean_price: float = 0.0
    target_high_price: float = 0.0
    target_low_price: float = 0.0
    upside_pct: float = 0.0
    recommendation_key: str = "none"
    number_of_analyst_opinions: int = 0
    market_cap: float = 0.0
    currency: str = "USD"
    raw_sector: str = ""
    raw_industry: str = ""
    raw_country: str = ""
    assigned_sector: str = "Sonstige / Unklassifiziert"
    assigned_country: str = "Sonstige / Global"
    is_holding: bool = False
    buy_in_price: float = 0.0
    quantity: float = 0.0
    gain_loss_abs: float = 0.0
    gain_loss_pct: float = 0.0
    passes_quantitative_filter: bool = False
    cluster_risk_warning: str = ""


class NewsArticle(BaseModel):
    """Represents a single news article with verified source URL."""

    title: str
    url: str
    source: str = "Web"
    published_at: str = ""
    snippet: str = ""


class AIAnalysisResult(BaseModel):
    """
    Pydantic schema enforced on Gemini LLM outputs for the 30-day Monthly Deep Dive analysis.
    Prevents hallucinated fields and enforces strict URL citation from input articles.
    """

    traffic_light: Literal["GREEN", "YELLOW", "RED"] = Field(
        ...,
        description="GREEN = Temporary overreaction/Buy opportunity, YELLOW = Hold/Watch, RED = Structural problem/Sell",
    )
    movement_cause: Literal[
        "TEMPORARY_OVERREACTION", "STRUCTURAL_PROBLEM", "NEUTRAL_OR_FAIRLY_VALUED"
    ] = Field(..., description="Root-cause classification of recent price and news development")
    summary: str = Field(..., description="Concise fundamental assessment based on the provided news articles")
    catalysts: List[str] = Field(default_factory=list, description="Key positive catalysts in the next 3-12 months")
    risks: List[str] = Field(default_factory=list, description="Key fundamental or macro risks")
    cited_urls: List[str] = Field(
        default_factory=list,
        description="Exact URLs from the provided news list that back this analysis",
    )


class ThesisRecord(BaseModel):
    """Persisted buy thesis record stored in data/portfolio_thesis.json."""

    ticker: str
    company_name: str
    saved_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    entry_price: float
    target_price: float
    traffic_light: Literal["GREEN", "YELLOW", "RED"] = "GREEN"
    movement_cause: str = "TEMPORARY_OVERREACTION"
    thesis_summary: str
    catalysts: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


class SentinelLLMOutput(BaseModel):
    """
    Pydantic schema enforced on Gemini LLM outputs for the Daily Sentinel thesis check.
    """

    status: Literal["CONFIRMED", "BROKEN", "UNTOUCHED"] = Field(
        ...,
        description="CONFIRMED = Catalyst occurred, BROKEN = Core thesis invalidated, UNTOUCHED = Market noise",
    )
    reasoning: str = Field(..., description="Clear explanation linking today's news to the original buy thesis")
    action_recommendation: str = Field(..., description="Concrete action advice for the retail investor")
    cited_urls: List[str] = Field(
        default_factory=list,
        description="Exact URLs from the provided 24h news articles",
    )


class SentinelAlert(BaseModel):
    """Result of a Daily Sentinel check for a portfolio position."""

    ticker: str
    company_name: str
    quantity: float = 0.0
    current_price: float = 0.0
    previous_close: float = 0.0
    daily_change_pct: float = 0.0
    triggered: bool = False
    has_saved_thesis: bool = False
    status: Literal["CONFIRMED", "BROKEN", "UNTOUCHED", "NORMAL"] = "NORMAL"
    reasoning: str = ""
    action_recommendation: str = ""
    cited_urls: List[str] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
