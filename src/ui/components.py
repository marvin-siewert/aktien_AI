"""
Reusable UI Components for Stock Evaluation Expander Cards (Interactive Price Chart + AI Analysis)
and Daily Sentinel Alerts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

import streamlit as st

from src.models.entities import (
    AIAnalysisResult,
    SentinelAlert,
    StockMetrics,
    ThesisRecord,
)
from src.services.ai_analyzer import AIAnalyzer
from src.services.market_data import MarketDataService
from src.services.news_fetcher import NewsFetcher
from src.storage.json_store import JsonStore
from src.ui.charts import build_stock_price_history_chart
from src.ui.i18n import I18nManager
from src.ui.theme_manager import ThemeConfig, get_theme


TIMEFRAME_OPTIONS: Dict[str, str] = {
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "3Y": "3y",
    "5Y": "5y",
    "MAX": "max",
}


def render_ai_evaluation_card(
    metrics: StockMetrics,
    store: JsonStore,
    market_data: MarketDataService,
    news_fetcher: NewsFetcher,
    ai_analyzer: AIAnalyzer,
    i18n: I18nManager,
    theme: Optional[ThemeConfig] = None,
    key_prefix: str = "card",
    is_highlighted: bool = False,
) -> None:
    """
    Render an interactive expander card for a holding or buy candidate:
    - When expanded, shows an interactive historical stock price chart with selectable
      timeframe (1M, 3M, 6M, 1Y, 3Y, 5Y, MAX).
    - Does NOT run AI analysis automatically; waits for user click on the AI analysis button.
    - If `is_highlighted=True` (selected via click in the Plotly scatterplot), wraps the card
      in a colored highlight banner and expands it automatically (`expanded=True`).
    """
    active_theme = theme or get_theme("clean_blue")
    role_badge = "💼 Bestand" if metrics.is_holding else "🎯 Kandidat"
    highlight_prefix = "🔶 [MARKIERT] " if is_highlighted else ""
    buy_in_info = (
        f"Kaufpreis: {metrics.buy_in_price:.2f} {metrics.currency} "
        f"(**G/V: {metrics.gain_loss_pct:+.1f}% / {metrics.gain_loss_abs:+.2f} {metrics.currency}**) | "
        if (metrics.is_holding and metrics.buy_in_price > 0)
        else ""
    )
    header = (
        f"{highlight_prefix}{role_badge} | **{metrics.name} ({metrics.ticker})** — "
        f"{buy_in_info}"
        f"Aktuell: {metrics.current_price:.2f} {metrics.currency} → "
        f"Ziel: {metrics.target_mean_price:.2f} {metrics.currency} "
        f"(**Upside: {metrics.upside_pct:+.1f}%** | {metrics.number_of_analyst_opinions} Analysten: `{metrics.recommendation_key.upper()}`) "
        f"[{metrics.assigned_sector} / {metrics.assigned_country}]"
    )

    state_key_analysis = f"ai_res_{key_prefix}_{metrics.ticker}"
    state_key_articles = f"news_res_{key_prefix}_{metrics.ticker}"

    if is_highlighted:
        border_col = "#FF2E93" if active_theme.key == "pink_unicorn" else "#FF8800"
        bg_col = "#FFE0F0" if active_theme.key == "pink_unicorn" else "#FFF7E6"
        st.markdown(
            f"""
            <div style="background-color: {bg_col}; border: 3px solid {border_col};
                        border-radius: 12px; padding: 10px 16px; margin-bottom: 6px;
                        box-shadow: 0 0 14px rgba(255, 136, 0, 0.28);">
                <strong>{i18n.t('highlighted_stock_banner')} {metrics.name} ({metrics.ticker})</strong>
                <span style="margin-left: 12px; font-size: 0.9rem;">
                    Branche: <em>{metrics.assigned_sector}</em> | Land: <em>{metrics.assigned_country}</em>
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander(header, expanded=is_highlighted):
        if metrics.cluster_risk_warning:
            st.warning(metrics.cluster_risk_warning)

        # ---------------------------------------------------------------------
        # 1. Interactive Historical Stock Price Chart (Timeframe Selector)
        # ---------------------------------------------------------------------
        tf_label = st.radio(
            "⏱️ Zeitraum für Aktienkurs-Chart:" if i18n.lang == "de" else "⏱️ Price Chart Timeframe:",
            options=list(TIMEFRAME_OPTIONS.keys()),
            index=3,  # Default: "1Y"
            horizontal=True,
            key=f"tf_sel_{key_prefix}_{metrics.ticker}",
        )
        yf_period = TIMEFRAME_OPTIONS[tf_label]
        hist_df = market_data.fetch_price_history(metrics.ticker, period=yf_period, use_cache=True)
        fig_hist = build_stock_price_history_chart(
            history_df=hist_df,
            ticker=metrics.ticker,
            company_name=metrics.name,
            currency=metrics.currency,
            target_price=metrics.target_mean_price,
            theme=active_theme,
            period_label=tf_label,
            buy_in_price=metrics.buy_in_price if metrics.is_holding else 0.0,
        )
        st.plotly_chart(
            fig_hist,
            use_container_width=True,
            key=f"hist_chart_{key_prefix}_{metrics.ticker}_{tf_label}",
        )

        # ---------------------------------------------------------------------
        # 2. On-Demand 30-Day Multi-Source News & AI Risk Analysis
        # ---------------------------------------------------------------------
        if st.button(
            i18n.t("btn_run_ai_analysis"),
            key=f"btn_ai_{key_prefix}_{metrics.ticker}",
            type="primary" if is_highlighted else "secondary",
        ):
            with st.spinner(
                f"Durchsuche Multi-Quellen-News (Finanzen, Skandale/Spionage, Politik/Restriktionen) & starte Risikoanalyse für {metrics.ticker}..."
            ):
                articles = news_fetcher.fetch_news(
                    ticker=metrics.ticker,
                    company_name=metrics.name,
                    days=30,
                    max_results=12,
                )
                analysis = ai_analyzer.analyze_monthly_deep_dive(
                    metrics=metrics,
                    articles=articles,
                    language=i18n.lang,
                )
                st.session_state[state_key_articles] = articles
                st.session_state[state_key_analysis] = analysis

        analysis_obj: Optional[AIAnalysisResult] = st.session_state.get(state_key_analysis)
        if analysis_obj:
            if analysis_obj.traffic_light == "GREEN":
                st.success(f"**{i18n.t('traffic_green')}** (`{analysis_obj.movement_cause}`)")
            elif analysis_obj.traffic_light == "RED":
                st.error(f"**{i18n.t('traffic_red')}** (`{analysis_obj.movement_cause}`)")
            else:
                st.warning(f"**{i18n.t('traffic_yellow')}** (`{analysis_obj.movement_cause}`)")

            st.markdown(f"**KI- & Risiko-Begründung:** {analysis_obj.summary}")

            col_cat, col_risk = st.columns(2)
            with col_cat:
                st.markdown("**Positive Katalysatoren:**")
                for cat in analysis_obj.catalysts:
                    st.markdown(f"- {cat}")
            with col_risk:
                st.markdown("**Erkannte Risiken (inkl. Skandal- & Politik-Scan):**")
                for rsk in analysis_obj.risks:
                    st.markdown(f"- {rsk}")

            st.markdown("**Geprüfte Original-Quellen (Anti-Halluzinations-Check):**")
            articles_cached = st.session_state.get(state_key_articles, [])
            url_to_title = {a.url: f"{a.title} ({a.source})" for a in articles_cached}
            for url in analysis_obj.cited_urls:
                label = url_to_title.get(url, url)
                st.markdown(f"- 🔗 [{label}]({url})")

            if st.button(
                i18n.t("btn_save_thesis"),
                key=f"btn_save_th_{key_prefix}_{metrics.ticker}",
                type="primary",
            ):
                record = ThesisRecord(
                    ticker=metrics.ticker,
                    company_name=metrics.name,
                    saved_at=datetime.now().isoformat(timespec="seconds"),
                    entry_price=metrics.current_price,
                    target_price=metrics.target_mean_price,
                    traffic_light=analysis_obj.traffic_light,
                    movement_cause=analysis_obj.movement_cause,
                    thesis_summary=analysis_obj.summary,
                    catalysts=analysis_obj.catalysts,
                    risks=analysis_obj.risks,
                    source_urls=analysis_obj.cited_urls,
                )
                store.save_thesis(metrics.ticker, record.model_dump())
                st.success(f"{i18n.t('msg_thesis_saved')} ({metrics.ticker})")


def render_sentinel_alert_card(alert: SentinelAlert, i18n: I18nManager) -> None:
    """Render a Daily Sentinel result card for a single portfolio holding."""
    if not alert.triggered:
        st.markdown(
            f"- **{alert.company_name} ({alert.ticker})**: `{alert.daily_change_pct:+.2f}%` "
            f"({alert.current_price:.2f}) — *{alert.reasoning}*"
        )
        return

    with st.container():
        if alert.status == "CONFIRMED":
            st.success(f"### {alert.company_name} ({alert.ticker}): {alert.daily_change_pct:+.2f}% — {i18n.t('status_confirmed')}")
        elif alert.status == "BROKEN":
            st.error(f"### {alert.company_name} ({alert.ticker}): {alert.daily_change_pct:+.2f}% — {i18n.t('status_broken')}")
        else:
            st.warning(f"### {alert.company_name} ({alert.ticker}): {alert.daily_change_pct:+.2f}% — {i18n.t('status_untouched')}")

        st.markdown(f"**Analyse:** {alert.reasoning}")
        st.markdown(f"**Handlungsempfehlung:** {alert.action_recommendation}")
        if alert.cited_urls:
            st.markdown("**24h-Nachrichtenquellen:**")
            for u in alert.cited_urls:
                st.markdown(f"- 🔗 [{u}]({u})")
        st.divider()
