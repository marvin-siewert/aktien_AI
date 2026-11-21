"""
Main Streamlit Web Application for the Modular Stock Analysis & Portfolio Monitoring System.

Features:
- Instant Language Switcher (Deutsch / English, extensible via `locales/*.json`)
- Instant Theme Switcher (Clean Blue & White / Pink Unicorn 🦄, extensible via `theme_manager.py`)
- Interactive Sector Filter ('Branchen-Filter') in both Portfolio and Monthly Deep Dive tabs
- Interactive Plotly Chart Click Selection: clicking a stock point in the scatterplot
  color-highlights and auto-expands the stock's evaluation card below (with a button to clear the marker)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.core.portfolio_manager import PortfolioManager
from src.core.risk_manager import RiskManager
from src.core.screener import DeepDiveScreeningResult, StockScreener
from src.core.sentinel_engine import SentinelEngine
from src.core.taxonomy_manager import TaxonomyManager
from src.models.entities import PortfolioState, StockMetrics
from src.services.ai_analyzer import AIAnalyzer
from src.services.market_data import MarketDataService
from src.services.news_fetcher import NewsFetcher
from src.storage.json_store import JsonStore
from src.ui.charts import (
    build_country_allocation_bar,
    build_diversification_sunburst,
    build_portfolio_target_price_chart,
    build_sector_allocation_bar,
    build_upside_coverage_scatter,
)
from src.ui.components import render_ai_evaluation_card, render_sentinel_alert_card
from src.ui.i18n import LANGUAGE_LABELS, I18nManager
from src.ui.portfolio_editor import render_portfolio_editor
from src.ui.theme_manager import THEMES, build_theme_css, get_theme


def init_session_state() -> None:
    """Initialize persistent Streamlit session state keys."""
    if "lang" not in st.session_state:
        st.session_state["lang"] = "de"
    if "theme_key" not in st.session_state:
        st.session_state["theme_key"] = "clean_blue"
    if "highlighted_ticker" not in st.session_state:
        st.session_state["highlighted_ticker"] = None
    if "chart_reset_counter" not in st.session_state:
        st.session_state["chart_reset_counter"] = 0


def _extract_clicked_ticker(chart_event: Any) -> Optional[str]:
    """Extract the clicked stock ticker from a Streamlit Plotly selection event dictionary."""
    if not chart_event:
        return None
    selection = chart_event.get("selection") if isinstance(chart_event, dict) else getattr(chart_event, "selection", None)
    if not selection:
        return None
    points = selection.get("points") if isinstance(selection, dict) else getattr(selection, "points", None)
    if not points or not isinstance(points, list):
        return None

    first_pt = points[0]
    if isinstance(first_pt, dict):
        custom = first_pt.get("customdata")
        if isinstance(custom, list) and custom:
            return str(custom[0]).strip().upper()
        if isinstance(custom, str) and custom.strip():
            return custom.strip().upper()
        text_val = first_pt.get("text")
        if isinstance(text_val, str) and text_val.strip():
            return text_val.strip().upper()
    return None


def clear_highlight_marker() -> None:
    """Clear the currently highlighted stock ticker and reset Plotly selection state."""
    st.session_state["highlighted_ticker"] = None
    st.session_state["chart_reset_counter"] = st.session_state.get("chart_reset_counter", 0) + 1


def _order_highlighted_first(items: List[StockMetrics], highlighted_ticker: Optional[str]) -> List[StockMetrics]:
    """Place the highlighted stock at the top of its section so the user immediately sees the expanded card."""
    if not highlighted_ticker:
        return items
    hl_upper = highlighted_ticker.upper()
    matched = [m for m in items if m.ticker.upper() == hl_upper]
    others = [m for m in items if m.ticker.upper() != hl_upper]
    return matched + others


def main() -> None:
    """Render the interactive Streamlit application."""
    load_dotenv(PROJECT_ROOT / ".env")
    st.set_page_config(
        page_title="Aktien-AI | Portfolio & Deep Dive",
        page_icon="📈",
        layout="wide",
    )
    init_session_state()

    # Initialize core services
    store = JsonStore()
    taxonomy = TaxonomyManager(store=store)
    market_data = MarketDataService(store=store, taxonomy_manager=taxonomy)
    pm = PortfolioManager(store=store, taxonomy=taxonomy, market_data=market_data)
    risk_manager = RiskManager()
    screener = StockScreener(market_data=market_data, risk_manager=risk_manager)
    news_fetcher = NewsFetcher()
    ai_analyzer = AIAnalyzer()
    sentinel_engine = SentinelEngine(
        store=store,
        market_data=market_data,
        news_fetcher=news_fetcher,
        ai_analyzer=ai_analyzer,
    )

    i18n = I18nManager(lang=st.session_state["lang"])

    # -------------------------------------------------------------------------
    # Top Control Bar & Sidebar (Language & Theme Switchers)
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.markdown(f"### ⚙️ {i18n.t('sidebar_settings')}")

        # Language toggle buttons
        st.caption(i18n.t("language_label"))
        lang_cols = st.columns(len(i18n.available_languages()))
        for idx, lang_code in enumerate(i18n.available_languages()):
            label = LANGUAGE_LABELS.get(lang_code, lang_code.upper())
            is_active = st.session_state["lang"] == lang_code
            with lang_cols[idx]:
                if st.button(
                    label,
                    key=f"btn_lang_{lang_code}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["lang"] = lang_code
                    st.rerun()

        st.divider()

        # Theme toggle buttons
        st.caption(i18n.t("theme_label"))
        for t_key, t_cfg in THEMES.items():
            is_active_theme = st.session_state["theme_key"] == t_key
            if st.button(
                f"{t_cfg.icon} {t_cfg.display_name}",
                key=f"btn_theme_{t_key}",
                use_container_width=True,
                type="primary" if is_active_theme else "secondary",
            ):
                st.session_state["theme_key"] = t_key
                st.rerun()

        st.divider()
        st.caption(f"**Depot:** {pm.state.portfolio_name} ({len(pm.state.positions)} Pos.)")
        st.caption(f"**Klassifikation:** {taxonomy.config.version_label}")
        if st.button(i18n.t("btn_clear_cache"), use_container_width=True):
            removed = store.clear_cache()
            st.toast(f"Cache geleert ({removed} Dateien entfernt).")

    active_theme = get_theme(st.session_state["theme_key"])
    st.markdown(build_theme_css(active_theme), unsafe_allow_html=True)

    # Header Banner
    unicorn_flair = " 🦄✨🌈" if active_theme.key == "pink_unicorn" else ""
    st.markdown(
        f"""
        <div class="theme-banner">
            <h1>{active_theme.icon} {i18n.t('app_title')}{unicorn_flair}</h1>
            <p>{i18n.t('app_subtitle')}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Main Navigation Tabs
    tab_port, tab_deep, tab_sent, tab_theses, tab_settings = st.tabs(
        [
            i18n.t("tab_portfolio"),
            i18n.t("tab_deep_dive"),
            i18n.t("tab_sentinel"),
            i18n.t("tab_theses"),
            i18n.t("tab_settings"),
        ]
    )

    # =========================================================================
    # TAB 1: Portfolio, Manual Editor, Snapshots, Sector Filter & Charts
    # =========================================================================
    with tab_port:
        render_portfolio_editor(pm=pm, i18n=i18n)

        # Sector filter for Tab 1 (Portfolio & Diversification)
        available_port_sectors = sorted(list({p.sector for p in pm.state.positions if p.sector}))
        selected_port_sectors = st.multiselect(
            i18n.t("filter_sectors_label"),
            options=taxonomy.config.sectors if taxonomy.config.sectors else available_port_sectors,
            default=[],
            placeholder=i18n.t("filter_sectors_placeholder"),
            key="port_sector_filter",
        )

        if selected_port_sectors:
            filtered_positions = [p for p in pm.state.positions if p.sector in selected_port_sectors]
            displayed_portfolio = PortfolioState(
                portfolio_name=pm.state.portfolio_name,
                updated_at=pm.state.updated_at,
                source=pm.state.source,
                positions=filtered_positions,
            )
        else:
            displayed_portfolio = pm.state

        risk_report = risk_manager.analyze_portfolio(displayed_portfolio, language=i18n.lang)

        # Top KPI Metrics Row
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(i18n.t("kpi_total_value"), f"{risk_report.total_value:,.2f} €")
        k2.metric(i18n.t("kpi_positions_count"), f"{risk_report.position_count}")
        k3.metric(
            i18n.t("kpi_max_position_weight"),
            f"{risk_report.largest_position_weight_pct:.1f}% ({risk_report.largest_position_ticker})",
        )
        k4.metric(
            i18n.t("kpi_max_sector_weight"),
            f"{risk_report.largest_sector_weight_pct:.1f}% ({risk_report.largest_sector_name[:18]})",
        )
        k5.metric(i18n.t("kpi_risk_violations"), str(len(risk_report.warnings)))

        # Cluster Risk Warnings
        st.markdown(f"### {i18n.t('section_risk_alerts')}")
        if not risk_report.warnings:
            st.success(i18n.t("risk_all_clear"))
        else:
            for warn in risk_report.warnings:
                st.warning(f"⚠️ {warn}")

        # Diversification Charts (Sunburst + Sector Bar + Country Bar)
        ch_col1, ch_col2 = st.columns([1.15, 1.0])
        with ch_col1:
            fig_sun = build_diversification_sunburst(
                displayed_portfolio,
                active_theme,
                title=i18n.t("chart_sunburst_title"),
            )
            st.plotly_chart(fig_sun, use_container_width=True)
        with ch_col2:
            fig_sec = build_sector_allocation_bar(
                risk_report,
                active_theme,
                title=i18n.t("chart_sector_bar_title"),
            )
            st.plotly_chart(fig_sec, use_container_width=True)

        fig_cnt = build_country_allocation_bar(
            risk_report,
            active_theme,
            title=i18n.t("chart_country_bar_title"),
        )
        st.plotly_chart(fig_cnt, use_container_width=True)

        # Chart 3: Current Holdings Price vs. Analyst Target Price
        holdings_tickers = [p.ticker for p in displayed_portfolio.positions]
        if holdings_tickers:
            holdings_metrics = market_data.fetch_batch_metrics(
                holdings_tickers,
                holding_tickers=set(holdings_tickers),
                use_cache=True,
            )
            fig_target = build_portfolio_target_price_chart(
                holdings_metrics,
                active_theme,
                title=i18n.t("chart_target_bar_title"),
            )
            st.plotly_chart(fig_target, use_container_width=True)

    # =========================================================================
    # TAB 2: Monthly Deep Dive (Screener, Sector Filter, Clickable Plot & AI Cards)
    # =========================================================================
    with tab_deep:
        st.markdown(f"## {i18n.t('deep_dive_header')}")
        st.caption(i18n.t("deep_dive_desc"))

        f_col1, f_col2, f_col3, f_col4 = st.columns([2.2, 1.3, 1.3, 1.5])
        with f_col1:
            scan_mode_choice = st.radio(
                i18n.t("scan_mode_label"),
                options=["quick", "full"],
                format_func=lambda m: i18n.t("scan_mode_quick") if m == "quick" else i18n.t("scan_mode_full"),
                horizontal=True,
            )
        with f_col2:
            min_analysts = st.number_input(i18n.t("filter_min_analysts"), min_value=1, max_value=60, value=12, step=1)
        with f_col3:
            min_upside = st.number_input(i18n.t("filter_min_upside"), min_value=-20.0, max_value=200.0, value=20.0, step=2.5)
        with f_col4:
            st.write("")
            run_scan_clicked = st.button(
                i18n.t("btn_run_screener"),
                type="primary",
                use_container_width=True,
            )

        # Sector Filter ('Branchen-Filter') and Name/Ticker Search for Monthly Deep Dive
        flt_col1, flt_col2 = st.columns([2.2, 1.8])
        with flt_col1:
            selected_dd_sectors = st.multiselect(
                i18n.t("filter_sectors_label"),
                options=taxonomy.config.sectors,
                default=[],
                placeholder=i18n.t("filter_sectors_placeholder"),
                key="deep_dive_sector_filter",
            )
        with flt_col2:
            search_query_dd = st.text_input(
                "🔎 Aktie nach Name oder Ticker suchen (z. B. Siemens Energy oder ENR.DE)"
                if i18n.lang == "de"
                else "🔎 Search stock by name or ticker (e.g. Siemens Energy or ENR.DE)",
                value="",
                placeholder="Name oder Ticker eingeben...",
                key="deep_dive_text_search",
            ).strip().lower()

        if run_scan_clicked or "deep_dive_result" not in st.session_state:
            progress_bar = st.progress(0, text="Starte Analysten-Screening...")

            def _update_progress(current: int, total: int, ticker_sym: str) -> None:
                pct = int((current / max(1, total)) * 100)
                progress_bar.progress(pct, text=f"Scanne {ticker_sym} ({current}/{total})...")

            dd_result = screener.run_deep_dive_scan(
                portfolio=pm.state,
                scan_mode=scan_mode_choice,
                min_analysts=int(min_analysts),
                min_upside_pct=float(min_upside),
                use_cache=True,
                language=i18n.lang,
                progress_callback=_update_progress,
            )
            progress_bar.empty()
            st.session_state["deep_dive_result"] = dd_result

        dd_res: DeepDiveScreeningResult = st.session_state["deep_dive_result"]

        # Apply Sector Filter and Name/Ticker Text Search to Holdings and Buy Candidates
        if selected_dd_sectors:
            filtered_holdings = [m for m in dd_res.holdings_metrics if m.assigned_sector in selected_dd_sectors]
            filtered_candidates = [m for m in dd_res.buy_candidates if m.assigned_sector in selected_dd_sectors]
        else:
            filtered_holdings = list(dd_res.holdings_metrics)
            filtered_candidates = list(dd_res.buy_candidates)

        if search_query_dd:
            filtered_holdings = [
                m for m in filtered_holdings
                if search_query_dd in m.ticker.lower() or search_query_dd in m.name.lower()
            ]
            # Also search across the full scanned universe if the user types a specific company name/ticker!
            universe_matches = [
                m for m in dd_res.universe_metrics
                if not m.is_holding and (search_query_dd in m.ticker.lower() or search_query_dd in m.name.lower())
            ]
            if selected_dd_sectors:
                universe_matches = [m for m in universe_matches if m.assigned_sector in selected_dd_sectors]
            filtered_candidates = universe_matches

        # Interactive Scatterplot with click-to-highlight
        st.caption(i18n.t("plot_click_hint"))
        scatter_items = filtered_holdings + filtered_candidates
        fig_scatter = build_upside_coverage_scatter(
            scatter_items,
            active_theme,
            title=i18n.t("chart_scatter_title"),
            min_analysts=int(min_analysts),
            min_upside_pct=float(min_upside),
            highlighted_ticker=st.session_state.get("highlighted_ticker"),
        )

        chart_key = "dd_scatter_interactive"
        scatter_event = st.plotly_chart(
            fig_scatter,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key=chart_key,
        )

        # Sync highlighted ticker directly with Plotly point selection:
        # - Clicking a point selects & highlights it
        # - Clicking another point switches the highlight to the new point
        # - Clicking the same point again deselects it in Plotly (clicked_ticker becomes None) -> highlight disappears
        clicked_ticker = _extract_clicked_ticker(scatter_event)
        st.session_state["highlighted_ticker"] = clicked_ticker
        active_highlight: Optional[str] = st.session_state.get("highlighted_ticker")

        # Section 1: Unbiased Re-Evaluation of Existing Holdings (highlighted stock moved to top)
        ordered_holdings = _order_highlighted_first(filtered_holdings, active_highlight)
        st.markdown(f"### {i18n.t('holdings_re_eval_title')} ({len(ordered_holdings)})")
        for hm in ordered_holdings:
            is_hl = bool(active_highlight and hm.ticker.upper() == active_highlight.upper())
            render_ai_evaluation_card(
                metrics=hm,
                store=store,
                market_data=market_data,
                news_fetcher=news_fetcher,
                ai_analyzer=ai_analyzer,
                i18n=i18n,
                theme=active_theme,
                key_prefix="hold",
                is_highlighted=is_hl,
            )

        st.divider()

        # Section 2: Top Undervalued Buy Candidates (highlighted stock moved to top)
        ordered_candidates = _order_highlighted_first(filtered_candidates, active_highlight)
        st.markdown(f"### {i18n.t('candidates_title')} ({len(ordered_candidates)})")
        for cand in ordered_candidates:
            is_hl = bool(active_highlight and cand.ticker.upper() == active_highlight.upper())
            render_ai_evaluation_card(
                metrics=cand,
                store=store,
                market_data=market_data,
                news_fetcher=news_fetcher,
                ai_analyzer=ai_analyzer,
                i18n=i18n,
                theme=active_theme,
                key_prefix="cand",
                is_highlighted=is_hl,
            )

    # =========================================================================
    # TAB 3: Daily Sentinel (Daily Price Jump Guard)
    # =========================================================================
    with tab_sent:
        st.markdown(f"## {i18n.t('sentinel_header')}")
        st.caption(i18n.t("sentinel_desc"))

        s_col1, s_col2 = st.columns([1.5, 2.5])
        with s_col1:
            threshold_val = st.number_input(
                i18n.t("sentinel_threshold_label"),
                min_value=0.5,
                max_value=50.0,
                value=5.0,
                step=0.5,
            )
        with s_col2:
            st.write("")
            if st.button(i18n.t("btn_run_sentinel"), type="primary"):
                with st.spinner("Prüfe Depot-Positionen auf Kurssprünge & 24h-News..."):
                    alerts = sentinel_engine.run_sentinel_check(
                        portfolio=pm.state,
                        threshold_pct=float(threshold_val),
                        use_cache=False,
                        language=i18n.lang,
                    )
                    st.session_state["sentinel_alerts"] = alerts

        sentinel_alerts = st.session_state.get("sentinel_alerts")
        if sentinel_alerts is not None:
            triggered_count = sum(1 for a in sentinel_alerts if a.triggered)
            if triggered_count == 0:
                st.success(i18n.t("sentinel_no_triggers"))
            for alert_item in sentinel_alerts:
                render_sentinel_alert_card(alert_item, i18n=i18n)

    # =========================================================================
    # TAB 4: Saved Buy Theses (data/portfolio_thesis.json)
    # =========================================================================
    with tab_theses:
        st.markdown(f"## {i18n.t('theses_header')}")
        saved_theses = store.load_theses()
        if not saved_theses:
            st.info(i18n.t("theses_empty"))
        else:
            for t_sym, th_data in saved_theses.items():
                with st.expander(
                    f"📌 **{th_data.get('company_name', t_sym)} ({t_sym})** — "
                    f"Einstieg: {th_data.get('entry_price', 0)} | Ziel: {th_data.get('target_price', 0)} "
                    f"| Status: `{th_data.get('traffic_light', 'GREEN')}` ({th_data.get('saved_at', '')})",
                    expanded=True,
                ):
                    st.markdown(f"**Kauf-These:** {th_data.get('thesis_summary', '')}")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Katalysatoren:**")
                        for c_item in th_data.get("catalysts", []):
                            st.markdown(f"- {c_item}")
                    with c2:
                        st.markdown("**Risiken:**")
                        for r_item in th_data.get("risks", []):
                            st.markdown(f"- {r_item}")
                    st.markdown("**Gespeicherte Quellen-URLs:**")
                    for u_item in th_data.get("source_urls", []):
                        st.markdown(f"- 🔗 [{u_item}]({u_item})")
                    if st.button(f"{i18n.t('btn_delete_thesis')} ({t_sym})", key=f"del_th_{t_sym}"):
                        store.delete_thesis(t_sym)
                        st.rerun()

    # =========================================================================
    # TAB 5: Settings & Sector / Country Taxonomy Editor + Version History
    # =========================================================================
    with tab_settings:
        st.markdown(f"## {i18n.t('settings_header')}")
        st.caption(i18n.t("settings_desc"))

        col_sec, col_cnt = st.columns(2)
        with col_sec:
            sectors_text = st.text_area(
                i18n.t("sectors_list_label"),
                value="\n".join(taxonomy.config.sectors),
                height=310,
                key="txt_sectors_editor",
            )
        with col_cnt:
            countries_text = st.text_area(
                i18n.t("countries_list_label"),
                value="\n".join(taxonomy.config.countries),
                height=310,
                key="txt_countries_editor",
            )

        v_col1, v_col2, v_col3 = st.columns([2, 1.5, 1.5])
        with v_col1:
            version_comment = st.text_input(
                i18n.t("taxonomy_version_name"),
                value="Eigene Anpassung",
                key="input_tax_version_label",
            )
        with v_col2:
            st.write("")
            if st.button(i18n.t("btn_save_taxonomy"), type="primary", use_container_width=True):
                new_s = [line.strip() for line in sectors_text.splitlines() if line.strip()]
                new_c = [line.strip() for line in countries_text.splitlines() if line.strip()]
                snap_path = taxonomy.update_lists(
                    new_sectors=new_s,
                    new_countries=new_c,
                    version_label=version_comment,
                    create_snapshot=True,
                )
                st.success(f"Listen gespeichert & Snapshot angelegt: {snap_path.name if snap_path else ''}")
                st.rerun()
        with v_col3:
            st.write("")
            if st.button(i18n.t("btn_reset_taxonomy"), use_container_width=True):
                taxonomy.reset_to_defaults(backup_current=True)
                st.success("Auf empfohlene Start-Listen zurückgesetzt (vorheriger Stand wurde gesichert).")
                st.rerun()

        st.divider()

        # Version History & Restore Section
        st.markdown(f"### 🕰️ {i18n.t('taxonomy_history_header')}")
        history_list = taxonomy.list_history_snapshots()
        if history_list:
            hist_map = {h["summary"]: h["filename"] for h in history_list}
            sel_hist = st.selectbox(
                i18n.t("select_taxonomy_version"),
                options=list(hist_map.keys()),
                key="sel_tax_hist",
            )
            if st.button(i18n.t("btn_restore_taxonomy")):
                restored = taxonomy.restore_snapshot(hist_map[sel_hist], backup_current=True)
                st.success(f"Listen-Version wiederhergestellt: {restored.version_label}")
                st.rerun()
        else:
            st.info("Noch keine historischen Listen-Snapshots vorhanden. Speichere oben eine Version, um die Historie zu starten.")

        st.divider()

        # Manual Per-Ticker Sector & Country Override Editor
        st.markdown(f"### 🎯 {i18n.t('overrides_header')}")
        ov_col1, ov_col2, ov_col3, ov_col4 = st.columns([1.5, 2, 2, 1.5])
        with ov_col1:
            ov_ticker = st.text_input("Ticker", placeholder="z. B. AMZN", key="ov_ticker_in")
        with ov_col2:
            ov_sector = st.selectbox("Branche", options=taxonomy.config.sectors, key="ov_sec_in")
        with ov_col3:
            ov_country = st.selectbox("Land", options=taxonomy.config.countries, key="ov_cnt_in")
        with ov_col4:
            st.write("")
            if st.button(i18n.t("btn_save_override"), use_container_width=True):
                if ov_ticker.strip():
                    taxonomy.set_ticker_override(ov_ticker, sector=ov_sector, country=ov_country, persist=True)
                    for pos in pm.state.positions:
                        if pos.ticker.upper() == ov_ticker.strip().upper():
                            pos.sector = ov_sector
                            pos.country = ov_country
                    pm.save_active()
                    st.success(f"Zuordnung für {ov_ticker.upper()} gespeichert.")
                    st.rerun()

        if taxonomy.config.ticker_overrides:
            ov_rows = [
                {"Ticker": k, "Manuelle Branche": v.get("sector", ""), "Manuelles Land": v.get("country", "")}
                for k, v in sorted(taxonomy.config.ticker_overrides.items())
            ]
            st.dataframe(pd.DataFrame(ov_rows), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
