"""
Plotly Interactive Charts Builder for Portfolio Diversification and Monthly Deep Dive.

Decouples chart construction from Streamlit state so all charts can be unit-tested
independently and styled dynamically with the active ThemeConfig.
Includes `customdata` with ticker symbols on scatter points and target-price bars
to support interactive click-selection (`on_select="rerun"`).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.core.risk_manager import PortfolioRiskReport
from src.core.taxonomy_manager import DEFAULT_SECTORS
from src.models.entities import PortfolioState, StockMetrics
from src.ui.theme_manager import ThemeConfig


def build_sector_color_map(sectors: List[str], theme: ThemeConfig) -> Dict[str, str]:
    """
    Build a deterministic high-contrast color mapping for every sector so each sector
    has a clearly distinguishable color across Sunburst, Bar, and Scatter charts.
    """
    palette = theme.color_sequence
    all_known = list(DEFAULT_SECTORS)
    for s in sectors:
        if s and s not in all_known:
            all_known.append(s)
    return {sec: palette[idx % len(palette)] for idx, sec in enumerate(all_known)}


def _apply_common_layout(fig: go.Figure, theme: ThemeConfig, title: str) -> go.Figure:
    """Apply consistent theme colors, background, and typography to a Plotly figure."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=17, color=theme.text_color)),
        template=theme.plotly_template,
        paper_bgcolor=theme.card_bg_color,
        plot_bgcolor=theme.bg_color,
        font=dict(color=theme.text_color),
        margin=dict(l=30, r=30, t=55, b=35),
        clickmode="event+select",
    )
    return fig


def build_diversification_sunburst(
    portfolio: PortfolioState,
    theme: ThemeConfig,
    title: str = "Branchen- & Länder-Verteilung",
) -> go.Figure:
    """
    Chart 1a: Interactive Sunburst chart showing hierarchy Sector -> Country -> Stock Ticker
    sized by market value.
    """
    if not portfolio.positions or portfolio.total_market_value <= 0:
        fig = go.Figure()
        return _apply_common_layout(fig, theme, title)

    rows = []
    for pos in portfolio.positions:
        rows.append(
            {
                "sector": pos.sector or "Sonstige",
                "country": pos.country or "Global",
                "ticker": f"{pos.ticker} ({pos.name[:18]})",
                "market_value": max(0.01, pos.market_value),
            }
        )
    df = pd.DataFrame(rows)
    sector_color_map = build_sector_color_map(df["sector"].unique().tolist(), theme)

    fig = px.sunburst(
        df,
        path=["sector", "country", "ticker"],
        values="market_value",
        color="sector",
        color_discrete_map=sector_color_map,
        color_discrete_sequence=theme.color_sequence,
    )
    fig.update_traces(textinfo="label+percent entry")
    return _apply_common_layout(fig, theme, title)


def build_sector_allocation_bar(
    risk_report: PortfolioRiskReport,
    theme: ThemeConfig,
    title: str = "Branchen-Gewichtung vs. Maximal-Limit",
) -> go.Figure:
    """
    Chart 1b: Bar chart comparing actual sector weights (%) against the configured
    maximum sector limit (e.g. 20%), highlighting limit violations in red.
    """
    fig = go.Figure()
    if not risk_report.sector_slices:
        return _apply_common_layout(fig, theme, title)

    categories = [s.category for s in risk_report.sector_slices]
    weights = [s.weight_pct for s in risk_report.sector_slices]
    counts = [
        f"{s.weight_pct:.1f}% ({s.stock_count} Aktie{'n' if s.stock_count != 1 else ''})"
        + (" ⚠️" if (s.exceeds_weight_cap or s.exceeds_count_cap) else "")
        for s in risk_report.sector_slices
    ]
    sector_color_map = build_sector_color_map(categories, theme)
    colors = [sector_color_map.get(s.category, theme.primary_color) for s in risk_report.sector_slices]
    line_colors = [
        theme.danger_color if (s.exceeds_weight_cap or s.exceeds_count_cap) else "rgba(0,0,0,0)"
        for s in risk_report.sector_slices
    ]
    line_widths = [3 if (s.exceeds_weight_cap or s.exceeds_count_cap) else 0 for s in risk_report.sector_slices]

    fig.add_trace(
        go.Bar(
            x=categories,
            y=weights,
            text=counts,
            textposition="outside",
            marker=dict(color=colors, line=dict(color=line_colors, width=line_widths)),
            name="Ist-Gewicht (%)",
        )
    )

    fig.add_hline(
        y=risk_report.max_sector_weight_cap_pct,
        line_dash="dash",
        line_color=theme.danger_color,
        annotation_text=f"Max Limit ({risk_report.max_sector_weight_cap_pct:.0f}%)",
        annotation_position="top right",
    )
    fig.update_yaxes(title_text="Depot-Gewicht (%)", range=[0, max(weights + [risk_report.max_sector_weight_cap_pct]) * 1.22])
    return _apply_common_layout(fig, theme, title)


def build_country_allocation_bar(
    risk_report: PortfolioRiskReport,
    theme: ThemeConfig,
    title: str = "Länder-Gewichtung im Depot (%)",
) -> go.Figure:
    """Chart 1c: Bar chart displaying geographic country allocation across the portfolio."""
    fig = go.Figure()
    if not risk_report.country_slices:
        return _apply_common_layout(fig, theme, title)

    countries = [c.category for c in risk_report.country_slices]
    weights = [c.weight_pct for c in risk_report.country_slices]
    labels = [f"{c.weight_pct:.1f}% ({c.stock_count})" for c in risk_report.country_slices]

    fig.add_trace(
        go.Bar(
            x=countries,
            y=weights,
            text=labels,
            textposition="outside",
            marker_color=theme.accent_color,
            name="Länder-Anteil (%)",
        )
    )
    fig.update_yaxes(title_text="Depot-Gewicht (%)", range=[0, max(weights + [25.0]) * 1.2])
    return _apply_common_layout(fig, theme, title)


def build_upside_coverage_scatter(
    metrics_list: List[StockMetrics],
    theme: ThemeConfig,
    title: str = "Upside (%) vs. Analysten-Abdeckung",
    min_analysts: int = 12,
    min_upside_pct: float = 20.0,
    highlighted_ticker: Optional[str] = None,
) -> go.Figure:
    """
    Chart 2: Interactive Scatterplot for Monthly Deep Dive:
    - X-axis: Number of Analysts
    - Y-axis: Target Price Upside (%)
    - Bubble size: Market Capitalization
    - Color: Assigned Sector ('Branche')
    - Symbol: Existing Holding vs. New Candidate
    - Supports clicking any point to highlight and expand the stock card below.
    """
    valid = [m for m in metrics_list if m.current_price > 0 and m.target_mean_price > 0]
    if not valid:
        fig = go.Figure()
        return _apply_common_layout(fig, theme, title)

    rows = []
    for m in valid:
        rows.append(
            {
                "Ticker": m.ticker,
                "Name": m.name,
                "Analysten": m.number_of_analyst_opinions,
                "Upside_Pct": m.upside_pct,
                "Branche": m.assigned_sector,
                "Land": m.assigned_country,
                "Status": "Bestandsaktie (Depot)" if m.is_holding else "Kauf-Kandidat",
                "Market_Cap_B": max(2.0, round(m.market_cap / 1e9, 1)),
                "Konsens": m.recommendation_key.upper(),
                "Aktueller_Kurs": f"{m.current_price:.2f} {m.currency}",
                "Kursziel": f"{m.target_mean_price:.2f} {m.currency}",
            }
        )
    df = pd.DataFrame(rows)
    sector_color_map = build_sector_color_map(df["Branche"].unique().tolist(), theme)

    fig = px.scatter(
        df,
        x="Analysten",
        y="Upside_Pct",
        size="Market_Cap_B",
        color="Branche",
        symbol="Status",
        symbol_map={"Bestandsaktie (Depot)": "diamond", "Kauf-Kandidat": "circle"},
        hover_name="Name",
        hover_data=["Ticker", "Branche", "Land", "Konsens", "Aktueller_Kurs", "Kursziel"],
        custom_data=["Ticker"],
        text="Ticker",
        color_discrete_map=sector_color_map,
        color_discrete_sequence=theme.color_sequence,
        size_max=42,
    )
    fig.update_traces(textposition="top center")

    # Reference threshold lines
    fig.add_hline(
        y=min_upside_pct,
        line_dash="dot",
        line_color=theme.positive_color,
        annotation_text=f"Min Upside ({min_upside_pct:.0f}%)",
    )
    fig.add_vline(
        x=min_analysts,
        line_dash="dot",
        line_color=theme.primary_color,
        annotation_text=f"Min Analysten ({min_analysts})",
    )
    fig.update_xaxes(title_text="Anzahl Analysten (Coverage)")
    fig.update_yaxes(title_text="Abstand zum Kursziel / Upside (%)")
    return _apply_common_layout(fig, theme, title)


def build_portfolio_target_price_chart(
    holdings_metrics: List[StockMetrics],
    theme: ThemeConfig,
    title: str = "Bestandsaktien: Aktueller Kurs vs. Analysten-Kursziel",
) -> go.Figure:
    """
    Chart 3: Horizontal bar chart of all existing holdings comparing current price vs. mean analyst
    target price, highlighting stocks that are near or above their target price (< 5% upside left).
    """
    fig = go.Figure()
    if not holdings_metrics:
        return _apply_common_layout(fig, theme, title)

    sorted_m = sorted(holdings_metrics, key=lambda x: x.upside_pct)
    labels = [
        f"{m.ticker} ({'⚠️ Ziel erreicht / Reallokation' if m.upside_pct < 5.0 else f'+{m.upside_pct:.1f}% Upside'})"
        for m in sorted_m
    ]
    tickers_custom = [[m.ticker] for m in sorted_m]
    current_prices = [m.current_price for m in sorted_m]
    target_prices = [m.target_mean_price for m in sorted_m]
    target_colors = [
        theme.warning_color if m.upside_pct < 5.0 else theme.positive_color
        for m in sorted_m
    ]

    fig.add_trace(
        go.Bar(
            y=labels,
            x=current_prices,
            customdata=tickers_custom,
            orientation="h",
            name="Aktueller Kurs",
            marker_color=theme.primary_color,
            text=[f"{p:.2f}" for p in current_prices],
            textposition="inside",
        )
    )
    fig.add_trace(
        go.Bar(
            y=labels,
            x=target_prices,
            customdata=tickers_custom,
            orientation="h",
            name="Analysten-Kursziel (Ø)",
            marker_color=target_colors,
            text=[f"Ziel: {t:.2f}" for t in target_prices],
            textposition="outside",
        )
    )
    fig.update_layout(barmode="group", height=max(360, 58 * len(sorted_m)))
    fig.update_xaxes(title_text="Kurs / Kursziel (in Handelswährung)")
    return _apply_common_layout(fig, theme, title)


def build_stock_price_history_chart(
    history_df: pd.DataFrame,
    ticker: str,
    company_name: str,
    currency: str,
    target_price: float,
    theme: ThemeConfig,
    period_label: str = "1Y",
) -> go.Figure:
    """
    Build an interactive historical stock price area/line chart over the user-selected timeframe,
    including period percentage return and optional analyst target price reference line.
    """
    fig = go.Figure()
    if history_df is None or history_df.empty or "Close" not in history_df.columns:
        return _apply_common_layout(fig, theme, f"{company_name} ({ticker}) — Kursverlauf")

    start_price = float(history_df["Close"].iloc[0])
    end_price = float(history_df["Close"].iloc[-1])
    perf_pct = ((end_price - start_price) / start_price) * 100.0 if start_price > 0 else 0.0
    line_color = theme.positive_color if perf_pct >= 0 else theme.danger_color

    fig.add_trace(
        go.Scatter(
            x=history_df["Date"],
            y=history_df["Close"],
            mode="lines",
            name=f"{ticker} Kurs ({currency})",
            line=dict(color=line_color, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(22, 163, 74, 0.10)" if perf_pct >= 0 else "rgba(220, 38, 38, 0.10)",
        )
    )

    if target_price > 0:
        fig.add_hline(
            y=target_price,
            line_dash="dash",
            line_color=theme.primary_color,
            annotation_text=f"Ø Analysten-Kursziel: {target_price:.2f} {currency}",
            annotation_position="top left",
        )

    title = (
        f"📈 {company_name} ({ticker}) — Zeitraum {period_label}: "
        f"{start_price:.2f} → {end_price:.2f} {currency} ({perf_pct:+.1f}%)"
    )
    fig.update_layout(height=340, hovermode="x unified")
    fig.update_xaxes(title_text="Datum")
    fig.update_yaxes(title_text=f"Kurs ({currency})")
    return _apply_common_layout(fig, theme, title)

