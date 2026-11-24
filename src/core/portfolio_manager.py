"""
Portfolio Manager for manual entry, live price enrichment, snapshot saving/loading,
and seamless broker/bank imports.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.taxonomy_manager import TaxonomyManager
from src.models.entities import PortfolioState, Position
from src.services.broker_adapters import (
    BankCsvImportAdapter,
    DemoPortfolioAdapter,
    ScalableCliAdapter,
)
from src.services.market_data import MarketDataService
from src.storage.json_store import JsonStore, sanitize_filename


class PortfolioManager:
    """
    Manages the active portfolio state (`data/portfolio_active.json`), saved portfolio snapshots
    (`data/portfolio_saved/`), manual position editing, and broker/CSV imports.
    """

    ACTIVE_FILE = "portfolio_active.json"

    def __init__(
        self,
        store: Optional[JsonStore] = None,
        taxonomy: Optional[TaxonomyManager] = None,
        market_data: Optional[MarketDataService] = None,
    ) -> None:
        self.store = store or JsonStore()
        self.taxonomy = taxonomy or TaxonomyManager(self.store)
        self.market_data = market_data or MarketDataService(self.store, self.taxonomy)
        self.state: PortfolioState = self.load_active()

    def load_active(self) -> PortfolioState:
        """Load the active portfolio from disk, falling back to the demo portfolio if none exists yet."""
        raw = self.store.read_json(self.ACTIVE_FILE)
        if isinstance(raw, dict) and isinstance(raw.get("positions"), list):
            try:
                state = PortfolioState(**raw)
                self._reapply_taxonomy_overrides(state)
                return state
            except Exception:
                pass

        demo = DemoPortfolioAdapter(self.store, self.taxonomy).load_demo_portfolio()
        self.store.write_json(self.ACTIVE_FILE, demo.model_dump())
        return demo

    def _reapply_taxonomy_overrides(self, state: PortfolioState) -> None:
        """Ensure positions reflect any explicit ticker overrides from TaxonomyManager."""
        for pos in state.positions:
            upper_t = pos.ticker.upper()
            if upper_t in self.taxonomy.config.ticker_overrides:
                ovr = self.taxonomy.config.ticker_overrides[upper_t]
                if ovr.get("sector") in self.taxonomy.config.sectors:
                    pos.sector = ovr["sector"]
                if ovr.get("country") in self.taxonomy.config.countries:
                    pos.country = ovr["country"]
            elif pos.sector not in self.taxonomy.config.sectors or pos.country not in self.taxonomy.config.countries:
                pos.sector, pos.country = self.taxonomy.classify_stock(
                    ticker=pos.ticker,
                    raw_sector=pos.sector,
                    raw_country=pos.country,
                )

    def save_active(self) -> Path:
        """Persist the current active portfolio state to data/portfolio_active.json."""
        self.state.updated_at = datetime.now().isoformat(timespec="seconds")
        return self.store.write_json(self.ACTIVE_FILE, self.state.model_dump())

    def add_or_update_position(
        self,
        ticker: str,
        quantity: float,
        buy_in_price: float = 0.0,
        name: str = "",
        sector: str = "",
        country: str = "",
        auto_enrich: bool = True,
    ) -> Position:
        """
        Add a new stock position or update an existing one by ticker.
        When `auto_enrich=True`, automatically fetches company name, current market price,
        currency, sector, and country via `MarketDataService` and `TaxonomyManager`.
        """
        clean_ticker = ticker.strip().upper()
        if not clean_ticker:
            raise ValueError("Ticker symbol must not be empty.")
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")

        current_price = buy_in_price
        currency = "EUR" if clean_ticker.endswith(".DE") else "USD"
        resolved_name = name.strip()
        resolved_sector = sector.strip()
        resolved_country = country.strip()

        if auto_enrich:
            metrics = self.market_data.fetch_stock_metrics(clean_ticker, use_cache=True, is_holding=True)
            if metrics.current_price > 0:
                current_price = metrics.current_price
            if not resolved_name or resolved_name == clean_ticker:
                resolved_name = metrics.name
            currency = metrics.currency
            if not resolved_sector:
                resolved_sector = metrics.assigned_sector
            if not resolved_country:
                resolved_country = metrics.assigned_country

        if not resolved_sector or resolved_sector not in self.taxonomy.config.sectors:
            resolved_sector, auto_country = self.taxonomy.classify_stock(clean_ticker)
            if not resolved_country:
                resolved_country = auto_country

        if not resolved_country or resolved_country not in self.taxonomy.config.countries:
            _, resolved_country = self.taxonomy.classify_stock(clean_ticker)

        effective_buy_in = buy_in_price if buy_in_price > 0 else current_price

        new_pos = Position(
            ticker=clean_ticker,
            name=resolved_name or clean_ticker,
            quantity=round(quantity, 4),
            buy_in_price=round(effective_buy_in, 2),
            current_price=round(current_price if current_price > 0 else effective_buy_in, 2),
            currency=currency,
            sector=resolved_sector,
            country=resolved_country,
        )

        # Replace existing ticker or append
        replaced = False
        for idx, existing in enumerate(self.state.positions):
            if existing.ticker.upper() == clean_ticker:
                new_pos.isin = existing.isin
                self.state.positions[idx] = new_pos
                replaced = True
                break
        if not replaced:
            self.state.positions.append(new_pos)

        self.state.source = "manual"
        self.save_active()
        return new_pos

    def remove_position(self, ticker: str) -> bool:
        """Remove a position by ticker from the active portfolio."""
        clean_ticker = ticker.strip().upper()
        before = len(self.state.positions)
        self.state.positions = [p for p in self.state.positions if p.ticker.upper() != clean_ticker]
        if len(self.state.positions) < before:
            self.save_active()
            return True
        return False

    def replace_positions(self, positions: List[Position], source: str = "manual") -> None:
        """Replace all positions in the active portfolio (e.g. after table edit) and persist."""
        valid_positions = [p for p in positions if p.ticker.strip() and p.quantity > 0]
        for pos in valid_positions:
            pos.ticker = pos.ticker.strip().upper()
            # Persist user-selected sector/country as ticker overrides if changed
            self.taxonomy.set_ticker_override(
                pos.ticker,
                sector=pos.sector,
                country=pos.country,
                persist=False,
            )
        self.taxonomy.save_active(create_snapshot=False)
        self.state.positions = valid_positions
        self.state.source = source
        self.save_active()

    def refresh_live_prices(self, use_cache: bool = False) -> None:
        """Refresh current market prices for all holdings via MarketDataService."""
        for pos in self.state.positions:
            metrics = self.market_data.fetch_stock_metrics(pos.ticker, use_cache=use_cache, is_holding=True)
            if metrics.current_price > 0:
                pos.current_price = metrics.current_price
            if not pos.name or pos.name == pos.ticker:
                pos.name = metrics.name
        self.save_active()

    # -------------------------------------------------------------------------
    # Saved Portfolio States / Snapshots (data/portfolio_saved/)
    # -------------------------------------------------------------------------
    def save_snapshot(self, snapshot_name: str) -> Path:
        """Save the current portfolio state under a user-defined name in data/portfolio_saved/."""
        clean_label = snapshot_name.strip() or self.state.portfolio_name or "Depot"
        self.state.portfolio_name = clean_label
        self.state.updated_at = datetime.now().isoformat(timespec="seconds")
        self.save_active()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_file = f"portfolio_{ts}_{sanitize_filename(clean_label)}.json"
        path = self.store.portfolio_saved_dir / safe_file
        return self.store.write_json(path, self.state.model_dump())

    def list_saved_snapshots(self) -> List[Dict[str, str]]:
        """List all saved portfolio snapshots in reverse chronological order."""
        items: List[Dict[str, str]] = []
        files = sorted(self.store.portfolio_saved_dir.glob("portfolio_*.json"), reverse=True)
        for fpath in files:
            raw = self.store.read_json(fpath)
            if isinstance(raw, dict):
                name = str(raw.get("portfolio_name", fpath.stem))
                updated = str(raw.get("updated_at", ""))
                positions = raw.get("positions", [])
                count = len(positions) if isinstance(positions, list) else 0
                items.append(
                    {
                        "filename": fpath.name,
                        "portfolio_name": name,
                        "updated_at": updated,
                        "summary": f"{name} ({updated}) — {count} Positionen",
                    }
                )
        return items

    def load_snapshot(self, filename: str) -> PortfolioState:
        """Load a saved portfolio state from data/portfolio_saved/<filename> as the active portfolio."""
        path = self.store.portfolio_saved_dir / filename
        raw = self.store.read_json(path)
        if not raw or not isinstance(raw, dict):
            raise FileNotFoundError(f"Saved portfolio '{filename}' not found.")
        self.state = PortfolioState(**raw)
        self._reapply_taxonomy_overrides(self.state)
        self.save_active()
        return self.state

    def delete_snapshot(self, filename: str) -> bool:
        """Delete a saved portfolio snapshot file from data/portfolio_saved/."""
        path = self.store.portfolio_saved_dir / filename
        if path.exists():
            path.unlink()
            return True
        return False

    # -------------------------------------------------------------------------
    # Direct Imports (Scalable CLI, Bank CSV, Demo)
    # -------------------------------------------------------------------------
    def import_from_scalable_cli(
        self,
        fallback_to_mock: bool = True,
        cli_cmd: Optional[str] = None,
    ) -> Tuple[PortfolioState, str]:
        """Import positions from Scalable Capital CLI (`sc broker holdings --json`)."""
        adapter = ScalableCliAdapter(cli_cmd=cli_cmd, store=self.store, taxonomy=self.taxonomy)
        state, msg = adapter.fetch_portfolio(fallback_to_mock=fallback_to_mock)
        if state.source == "scalable_cli" or fallback_to_mock:
            self.state = state
            self.save_active()
        return self.state, msg

    def import_from_csv(self, csv_text: str, portfolio_name: str = "Bank-CSV-Import") -> PortfolioState:
        """Import positions from a bank or broker CSV string."""
        adapter = BankCsvImportAdapter(taxonomy=self.taxonomy)
        state = adapter.parse_csv_content(csv_text, portfolio_name=portfolio_name)
        self.state = state
        self.save_active()
        return self.state

    def load_demo_portfolio(self) -> PortfolioState:
        """Load the curated demo portfolio from data/mock_portfolio.json."""
        adapter = DemoPortfolioAdapter(store=self.store, taxonomy=self.taxonomy)
        self.state = adapter.load_demo_portfolio()
        self.save_active()
        return self.state
