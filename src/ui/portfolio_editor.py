"""
Portfolio Editor UI Component for manual position entry, live table editing,
portfolio snapshot saving/loading, and equal-ranking broker/CSV imports.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.core.portfolio_manager import PortfolioManager
from src.models.entities import Position
from src.ui.i18n import I18nManager


def render_portfolio_editor(pm: PortfolioManager, i18n: I18nManager) -> None:
    """
    Render the 3-mode Portfolio Management workspace:
    1. Manual Quick-Add & Interactive Data Table Editor
    2. Save & Load Named Portfolio Snapshots
    3. Direct Broker & Bank Imports (Scalable CLI, Universal Bank CSV, Demo Portfolio)
    """
    with st.expander(i18n.t("portfolio_editor_expander"), expanded=True):
        sub_tab_manual, sub_tab_snapshots, sub_tab_import = st.tabs(
            [
                f"✍️ {i18n.t('portfolio_mode_manual')}",
                f"💾 {i18n.t('portfolio_mode_snapshots')}",
                f"🏦 {i18n.t('portfolio_mode_import')}",
            ]
        )

        # ---------------------------------------------------------------------
        # Sub-Tab 1: Manual Quick-Add & Inline Table Editor
        # ---------------------------------------------------------------------
        with sub_tab_manual:
            st.markdown(f"**{i18n.t('quick_add_header')}**")
            col_t, col_q, col_b, col_btn = st.columns([2, 1.5, 1.5, 2])
            with col_t:
                in_ticker = st.text_input(i18n.t("input_ticker"), key="qa_ticker", placeholder="z. B. AAPL, SAP.DE")
            with col_q:
                in_qty = st.number_input(i18n.t("input_quantity"), min_value=0.01, value=10.0, step=1.0, key="qa_qty")
            with col_b:
                in_buy_in = st.number_input(i18n.t("input_buy_in"), min_value=0.0, value=0.0, step=1.0, key="qa_buyin")
            with col_btn:
                st.write("")
                st.write("")
                if st.button(i18n.t("btn_add_position"), use_container_width=True, type="primary"):
                    if in_ticker.strip():
                        added = pm.add_or_update_position(
                            ticker=in_ticker,
                            quantity=float(in_qty),
                            buy_in_price=float(in_buy_in),
                            auto_enrich=True,
                        )
                        st.success(f"{i18n.t('msg_position_added')} {added.name} ({added.ticker})")
                        st.rerun()

            # Build editable DataFrame for current positions
            rows = []
            for pos in pm.state.positions:
                rows.append(
                    {
                        "Ticker": pos.ticker,
                        "Name": pos.name,
                        "Quantity": float(pos.quantity),
                        "Buy_In_Price": float(pos.buy_in_price),
                        "Current_Price": float(pos.current_price),
                        "Market_Value": float(pos.market_value),
                        "Gain_Loss_Pct": float(pos.gain_loss_pct),
                        "Currency": pos.currency,
                        "Sector": pos.sector if pos.sector in pm.taxonomy.config.sectors else pm.taxonomy.config.sectors[-1],
                        "Country": pos.country if pos.country in pm.taxonomy.config.countries else pm.taxonomy.config.countries[-1],
                    }
                )
            df = pd.DataFrame(rows) if rows else pd.DataFrame(
                columns=[
                    "Ticker", "Name", "Quantity", "Buy_In_Price", "Current_Price",
                    "Market_Value", "Gain_Loss_Pct", "Currency", "Sector", "Country",
                ]
            )

            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                key="portfolio_inline_editor",
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", required=True),
                    "Name": st.column_config.TextColumn("Name"),
                    "Quantity": st.column_config.NumberColumn("Stück / Shares", min_value=0.0, format="%.2f", required=True),
                    "Buy_In_Price": st.column_config.NumberColumn("Einstand / Buy-In", min_value=0.0, format="%.2f"),
                    "Current_Price": st.column_config.NumberColumn("Akt. Kurs", min_value=0.0, format="%.2f"),
                    "Market_Value": st.column_config.NumberColumn("Marktwert", disabled=True, format="%.2f"),
                    "Gain_Loss_Pct": st.column_config.NumberColumn("G/V (%)", disabled=True, format="%.2f %%"),
                    "Currency": st.column_config.TextColumn("Währung", default="EUR"),
                    "Sector": st.column_config.SelectboxColumn(
                        "Branche (Sector)",
                        options=pm.taxonomy.config.sectors,
                        required=True,
                    ),
                    "Country": st.column_config.SelectboxColumn(
                        "Land (Country)",
                        options=pm.taxonomy.config.countries,
                        required=True,
                    ),
                },
            )

            c_save, c_refresh = st.columns(2)
            with c_save:
                if st.button(i18n.t("btn_save_table_changes"), use_container_width=True):
                    updated_positions = []
                    for _, row in edited_df.iterrows():
                        t_val = str(row.get("Ticker") or "").strip().upper()
                        q_val = float(row.get("Quantity") or 0.0)
                        if not t_val or q_val <= 0:
                            continue
                        b_val = float(row.get("Buy_In_Price") or 0.0)
                        c_val = float(row.get("Current_Price") or b_val)
                        updated_positions.append(
                            Position(
                                ticker=t_val,
                                name=str(row.get("Name") or t_val),
                                quantity=q_val,
                                buy_in_price=b_val,
                                current_price=c_val if c_val > 0 else b_val,
                                currency=str(row.get("Currency") or "EUR"),
                                sector=str(row.get("Sector") or pm.taxonomy.config.sectors[-1]),
                                country=str(row.get("Country") or pm.taxonomy.config.countries[-1]),
                            )
                        )
                    pm.replace_positions(updated_positions, source="manual")
                    st.success(i18n.t("msg_portfolio_saved"))
                    st.rerun()
            with c_refresh:
                if st.button(i18n.t("btn_refresh_prices"), use_container_width=True):
                    pm.refresh_live_prices(use_cache=False)
                    st.rerun()

        # ---------------------------------------------------------------------
        # Sub-Tab 2: Save & Load Named Portfolio Snapshots
        # ---------------------------------------------------------------------
        with sub_tab_snapshots:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                snap_name = st.text_input(
                    i18n.t("snapshot_name_input"),
                    value=pm.state.portfolio_name,
                    key="input_snap_name",
                )
                if st.button(i18n.t("btn_save_snapshot"), use_container_width=True, type="primary"):
                    saved_path = pm.save_snapshot(snap_name)
                    st.success(f"{i18n.t('msg_portfolio_saved')} {saved_path.name}")
                    st.rerun()

                # Direct JSON export button
                st.download_button(
                    label="⬇️ Aktuelles Depot als JSON exportieren",
                    data=pm.state.model_dump_json(indent=2),
                    file_name=f"{pm.state.portfolio_name.replace(' ', '_')}.json",
                    mime="application/json",
                    use_container_width=True,
                )

            with col_s2:
                snapshots = pm.list_saved_snapshots()
                if snapshots:
                    options = {s["summary"]: s["filename"] for s in snapshots}
                    selected_summary = st.selectbox(
                        i18n.t("select_snapshot_load"),
                        options=list(options.keys()),
                        key="sel_snap_load",
                    )
                    b_load, b_del = st.columns(2)
                    with b_load:
                        if st.button(i18n.t("btn_load_snapshot"), use_container_width=True):
                            fname = options[selected_summary]
                            loaded = pm.load_snapshot(fname)
                            st.success(f"{i18n.t('msg_portfolio_loaded')} {loaded.portfolio_name}")
                            st.rerun()
                    with b_del:
                        if st.button(i18n.t("btn_delete_snapshot"), use_container_width=True):
                            fname = options[selected_summary]
                            pm.delete_snapshot(fname)
                            st.rerun()
                else:
                    st.info("Noch keine separaten Depot-Stände in 'data/portfolio_saved/' gespeichert.")

        # ---------------------------------------------------------------------
        # Sub-Tab 3: Equal-Ranking Broker & Bank Imports
        # ---------------------------------------------------------------------
        with sub_tab_import:
            col_imp1, col_imp2, col_imp3 = st.columns(3)
            with col_imp1:
                st.markdown(f"#### {i18n.t('import_scalable_title')}")
                st.caption(i18n.t("import_scalable_desc"))
                if st.button(i18n.t("btn_import_scalable"), use_container_width=True):
                    _, msg = pm.import_from_scalable_cli(fallback_to_mock=True)
                    st.info(msg)
                    st.rerun()

            with col_imp2:
                st.markdown(f"#### {i18n.t('import_csv_title')}")
                st.caption(i18n.t("import_csv_desc"))
                uploaded_csv = st.file_uploader("CSV-Datei wählen", type=["csv", "txt"], key="bank_csv_uploader")
                if uploaded_csv is not None:
                    content = uploaded_csv.getvalue().decode("utf-8", errors="replace")
                    imported = pm.import_from_csv(content, portfolio_name=uploaded_csv.name)
                    st.success(f"CSV importiert: {len(imported.positions)} Positionen geladen.")
                    st.rerun()

            with col_imp3:
                st.markdown(f"#### {i18n.t('import_demo_title')}")
                st.caption("Lädt das Beispiel-Depot (DAX & US Core) aus data/mock_portfolio.json.")
                if st.button(i18n.t("btn_load_demo"), use_container_width=True):
                    pm.load_demo_portfolio()
                    st.rerun()
