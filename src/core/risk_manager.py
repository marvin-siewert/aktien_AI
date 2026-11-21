"""
Anti-Cluster-Risk & Portfolio Diversification Manager.

Evaluates portfolio diversification across:
- Single Position Weight Limit (default max 5.0% per stock; target 20-25 stocks)
- Sector ('Branche') Limits (default max 3 stocks per sector and max 20.0% weight per sector)
- Country ('Land') Allocation Breakdown
- Pre-trade cluster risk check for new buy candidates
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from src.models.entities import PortfolioState, StockMetrics


@dataclass
class AllocationSlice:
    """Represents weight and stock count for a single sector or country."""

    category: str
    market_value: float
    weight_pct: float
    stock_count: int
    tickers: List[str] = field(default_factory=list)
    exceeds_weight_cap: bool = False
    exceeds_count_cap: bool = False


@dataclass
class PortfolioRiskReport:
    """Comprehensive diversification and cluster-risk report for a portfolio."""

    total_value: float
    position_count: int
    target_min_positions: int
    target_max_positions: int
    max_position_weight_cap_pct: float
    max_sector_weight_cap_pct: float
    max_stocks_per_sector_cap: int
    largest_position_ticker: str
    largest_position_weight_pct: float
    largest_sector_name: str
    largest_sector_weight_pct: float
    position_weights: Dict[str, float]
    sector_slices: List[AllocationSlice]
    country_slices: List[AllocationSlice]
    warnings: List[str]


class RiskManager:
    """
    Calculates portfolio weights, sector/country distributions, and enforces anti-cluster-risk rules.
    """

    def __init__(
        self,
        max_position_weight_pct: float = 5.0,
        max_sector_weight_pct: float = 20.0,
        max_stocks_per_sector: int = 3,
        target_min_positions: int = 20,
        target_max_positions: int = 25,
    ) -> None:
        self.max_position_weight_pct = max_position_weight_pct
        self.max_sector_weight_pct = max_sector_weight_pct
        self.max_stocks_per_sector = max_stocks_per_sector
        self.target_min_positions = target_min_positions
        self.target_max_positions = target_max_positions

    def analyze_portfolio(self, portfolio: PortfolioState, language: str = "de") -> PortfolioRiskReport:
        """Compute full diversification breakdown and generate human-readable risk warnings."""
        is_de = language.lower().startswith("de")
        total_val = portfolio.total_market_value
        positions = portfolio.positions
        pos_count = len(positions)

        position_weights: Dict[str, float] = {}
        sector_totals: Dict[str, float] = {}
        sector_tickers: Dict[str, List[str]] = {}
        country_totals: Dict[str, float] = {}
        country_tickers: Dict[str, List[str]] = {}

        warnings: List[str] = []

        for pos in positions:
            val = pos.market_value
            weight = round((val / total_val) * 100.0, 2) if total_val > 0 else 0.0
            position_weights[pos.ticker] = weight

            if weight > self.max_position_weight_pct:
                msg = (
                    f"Einzelpositions-Limit überschritten: {pos.name} ({pos.ticker}) hat {weight:.1f}% Gewicht "
                    f"(Maximal erlaubt: {self.max_position_weight_pct:.1f}%)."
                    if is_de
                    else f"Single-position cap exceeded: {pos.name} ({pos.ticker}) is at {weight:.1f}% weight "
                    f"(Max allowed: {self.max_position_weight_pct:.1f}%)."
                )
                warnings.append(msg)

            sec = pos.sector or "Sonstige / Unklassifiziert"
            sector_totals[sec] = sector_totals.get(sec, 0.0) + val
            sector_tickers.setdefault(sec, []).append(pos.ticker)

            cnt = pos.country or "Sonstige / Global"
            country_totals[cnt] = country_totals.get(cnt, 0.0) + val
            country_tickers.setdefault(cnt, []).append(pos.ticker)

        # Build Sector Slices
        sector_slices: List[AllocationSlice] = []
        for sec, val in sorted(sector_totals.items(), key=lambda x: x[1], reverse=True):
            w_pct = round((val / total_val) * 100.0, 2) if total_val > 0 else 0.0
            t_list = sector_tickers[sec]
            c_count = len(t_list)
            exceeds_w = w_pct > self.max_sector_weight_pct
            exceeds_c = c_count > self.max_stocks_per_sector

            if exceeds_w:
                warnings.append(
                    f"Branchen-Gewicht überschritten: '{sec}' macht {w_pct:.1f}% des Depots aus "
                    f"(Limit: {self.max_sector_weight_pct:.1f}%)."
                    if is_de
                    else f"Sector weight cap exceeded: '{sec}' accounts for {w_pct:.1f}% of portfolio "
                    f"(Cap: {self.max_sector_weight_pct:.1f}%)."
                )
            if exceeds_c:
                warnings.append(
                    f"Branchen-Anzahl überschritten: '{sec}' enthält {c_count} Aktien ({', '.join(t_list)}) "
                    f"– Maximal {self.max_stocks_per_sector} Aktien pro Branche erlaubt."
                    if is_de
                    else f"Sector stock count exceeded: '{sec}' has {c_count} stocks ({', '.join(t_list)}) "
                    f"– Max {self.max_stocks_per_sector} stocks per sector allowed."
                )

            sector_slices.append(
                AllocationSlice(
                    category=sec,
                    market_value=round(val, 2),
                    weight_pct=w_pct,
                    stock_count=c_count,
                    tickers=t_list,
                    exceeds_weight_cap=exceeds_w,
                    exceeds_count_cap=exceeds_c,
                )
            )

        # Build Country Slices
        country_slices: List[AllocationSlice] = []
        for cnt, val in sorted(country_totals.items(), key=lambda x: x[1], reverse=True):
            w_pct = round((val / total_val) * 100.0, 2) if total_val > 0 else 0.0
            t_list = country_tickers[cnt]
            country_slices.append(
                AllocationSlice(
                    category=cnt,
                    market_value=round(val, 2),
                    weight_pct=w_pct,
                    stock_count=len(t_list),
                    tickers=t_list,
                )
            )

        if 0 < pos_count < self.target_min_positions:
            warnings.append(
                f"Diversifikations-Hinweis: Aktuell {pos_count} Aktien im Depot "
                f"(Zielkorridor für <5% Einzelrisiko: {self.target_min_positions}–{self.target_max_positions} Aktien)."
                if is_de
                else f"Diversification note: Currently {pos_count} holdings in portfolio "
                f"(Target range for <5% single-stock risk: {self.target_min_positions}–{self.target_max_positions} stocks)."
            )

        largest_pos_ticker = "-"
        largest_pos_weight = 0.0
        if position_weights:
            largest_pos_ticker, largest_pos_weight = max(position_weights.items(), key=lambda x: x[1])

        largest_sec_name = sector_slices[0].category if sector_slices else "-"
        largest_sec_weight = sector_slices[0].weight_pct if sector_slices else 0.0

        return PortfolioRiskReport(
            total_value=total_val,
            position_count=pos_count,
            target_min_positions=self.target_min_positions,
            target_max_positions=self.target_max_positions,
            max_position_weight_cap_pct=self.max_position_weight_pct,
            max_sector_weight_cap_pct=self.max_sector_weight_pct,
            max_stocks_per_sector_cap=self.max_stocks_per_sector,
            largest_position_ticker=largest_pos_ticker,
            largest_position_weight_pct=largest_pos_weight,
            largest_sector_name=largest_sec_name,
            largest_sector_weight_pct=largest_sec_weight,
            position_weights=position_weights,
            sector_slices=sector_slices,
            country_slices=country_slices,
            warnings=warnings,
        )

    def check_candidate_cluster_risk(
        self,
        candidate: StockMetrics,
        portfolio: PortfolioState,
        language: str = "de",
    ) -> str:
        """
        Check if buying a new candidate stock would violate the sector stock count (max 3)
        or sector weight (max 20%) limits of the current portfolio.
        Returns an empty string if compliant, or a warning text if restricted.
        """
        is_de = language.lower().startswith("de")
        report = self.analyze_portfolio(portfolio, language=language)
        sec_map = {s.category: s for s in report.sector_slices}
        sec_slice = sec_map.get(candidate.assigned_sector)
        if not sec_slice:
            return ""

        if sec_slice.stock_count >= self.max_stocks_per_sector:
            return (
                f"⚠️ Branchen-Limit erreicht: Bereits {sec_slice.stock_count}/{self.max_stocks_per_sector} Aktien "
                f"in '{candidate.assigned_sector}' ({', '.join(sec_slice.tickers)})."
                if is_de
                else f"⚠️ Sector count cap reached: Already {sec_slice.stock_count}/{self.max_stocks_per_sector} stocks "
                f"in '{candidate.assigned_sector}' ({', '.join(sec_slice.tickers)})."
            )
        if sec_slice.weight_pct >= self.max_sector_weight_pct:
            return (
                f"⚠️ Branchen-Gewicht erreicht: '{candidate.assigned_sector}' liegt bereits bei {sec_slice.weight_pct:.1f}% "
                f"(Max: {self.max_sector_weight_pct:.1f}%)."
                if is_de
                else f"⚠️ Sector weight cap reached: '{candidate.assigned_sector}' is already at {sec_slice.weight_pct:.1f}% "
                f"(Max: {self.max_sector_weight_pct:.1f}%)."
            )
        return ""
