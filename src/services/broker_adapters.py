"""
Modular Broker and Bank Import Adapters (Read-Only).

Supports:
1. Official Scalable Capital CLI (`ScalableCapital/scalable-cli` via `sc broker holdings --json`)
2. Universal Bank / Neobroker CSV Importer (Scalable, Trade Republic, ING, Comdirect, Portfolio Performance)
3. Demo / Mock Portfolio Loader (`data/mock_portfolio.json`)
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.taxonomy_manager import TaxonomyManager
from src.models.entities import PortfolioState, Position
from src.storage.json_store import JsonStore


def parse_localized_float(value: Any, default: float = 0.0) -> float:
    """Parse standard or German-formatted numbers (e.g. '1.234,56' or '123.45 €') into float."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    # Strip currency symbols and whitespace
    for token in ("€", "$", "EUR", "USD", "CHF", "GBP", "%", " "):
        text = text.replace(token, "")
    if "," in text and "." in text:
        # Determine whether comma or dot is the decimal separator
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return default


class ScalableCliAdapter:
    """
    Read-only subprocess adapter for the official Scalable Capital CLI (`sc`).
    Executes `sc broker holdings --json` and maps holdings into Position entities.
    """

    def __init__(
        self,
        cli_cmd: Optional[str] = None,
        store: Optional[JsonStore] = None,
        taxonomy: Optional[TaxonomyManager] = None,
    ) -> None:
        self.cli_cmd = cli_cmd or os.getenv("SCALABLE_CLI_CMD", "sc")
        self.store = store or JsonStore()
        self.taxonomy = taxonomy or TaxonomyManager(self.store)

    def fetch_portfolio(self, fallback_to_mock: bool = True) -> Tuple[PortfolioState, str]:
        """
        Execute `sc broker holdings --json` in read-only mode.
        Returns (PortfolioState, status_message).
        If the CLI is not installed or not logged in, falls back to mock_portfolio.json when enabled.
        """
        cmd = [self.cli_cmd, "broker", "holdings", "--json"]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                positions = self.parse_cli_json(proc.stdout)
                if positions:
                    state = PortfolioState(
                        portfolio_name="Scalable Capital (CLI Live)",
                        updated_at=datetime.now().isoformat(timespec="seconds"),
                        source="scalable_cli",
                        positions=positions,
                    )
                    return state, "Successfully imported holdings from Scalable Capital CLI."
            error_detail = (proc.stderr or proc.stdout or "Non-zero exit code").strip()
        except FileNotFoundError:
            error_detail = f"Scalable CLI executable '{self.cli_cmd}' not found on PATH."
        except subprocess.TimeoutExpired:
            error_detail = "Scalable CLI command timed out after 15 seconds."
        except Exception as exc:
            error_detail = str(exc)

        if fallback_to_mock:
            demo_state = DemoPortfolioAdapter(self.store, self.taxonomy).load_demo_portfolio()
            return (
                demo_state,
                f"Scalable CLI unavailable ({error_detail}). Loaded mock portfolio fallback.",
            )

        raise RuntimeError(f"Scalable CLI import failed: {error_detail}")

    def parse_cli_json(self, raw_json: str) -> List[Position]:
        """
        Parse the JSON output of `sc broker holdings --json`.
        Handles list envelopes as well as `{'holdings': [...]}` or `{'data': {'positions': [...]}}`.
        """
        payload = json.loads(raw_json)
        items: List[Dict[str, Any]] = []
        if isinstance(payload, list):
            items = [x for x in payload if isinstance(x, dict)]
        elif isinstance(payload, dict):
            if isinstance(payload.get("holdings"), list):
                items = payload["holdings"]
            elif isinstance(payload.get("positions"), list):
                items = payload["positions"]
            elif isinstance(payload.get("data"), dict):
                data_obj = payload["data"]
                items = data_obj.get("holdings") or data_obj.get("positions") or []
            elif isinstance(payload.get("data"), list):
                items = payload["data"]

        positions: List[Position] = []
        for item in items:
            ticker = str(
                item.get("ticker")
                or item.get("symbol")
                or item.get("isin")
                or ""
            ).strip().upper()
            if not ticker:
                continue
            quantity = parse_localized_float(
                item.get("quantity") or item.get("shares") or item.get("amount"), 0.0
            )
            if quantity <= 0:
                continue
            buy_in = parse_localized_float(
                item.get("averagePrice")
                or item.get("buyInPrice")
                or item.get("buy_in_price")
                or item.get("purchasePrice"),
                0.0,
            )
            current_price = parse_localized_float(
                item.get("currentPrice")
                or item.get("price")
                or item.get("lastPrice")
                or item.get("current_price"),
                buy_in,
            )
            name = str(item.get("name") or item.get("title") or ticker).strip()
            isin = str(item.get("isin") or "").strip().upper()
            currency = str(item.get("currency") or "EUR").strip().upper()
            raw_sector = str(item.get("sector") or "")
            raw_country = str(item.get("country") or "")

            sector, country = self.taxonomy.classify_stock(
                ticker=ticker,
                raw_sector=raw_sector,
                raw_country=raw_country,
            )

            positions.append(
                Position(
                    ticker=ticker,
                    isin=isin,
                    name=name,
                    quantity=quantity,
                    buy_in_price=buy_in,
                    current_price=current_price if current_price > 0 else buy_in,
                    currency=currency,
                    sector=sector,
                    country=country,
                )
            )
        return positions


class BankCsvImportAdapter:
    """
    Universal CSV importer for bank and broker portfolio exports
    (Scalable Capital, Trade Republic, ING, Comdirect, DKB, Portfolio Performance, Parqet).
    """

    def __init__(self, taxonomy: Optional[TaxonomyManager] = None) -> None:
        self.taxonomy = taxonomy or TaxonomyManager()

    def parse_csv_content(self, csv_text: str, portfolio_name: str = "CSV-Bank-Import") -> PortfolioState:
        """Auto-detect delimiter and column headers to parse a bank/broker CSV into a PortfolioState."""
        cleaned = csv_text.lstrip("\ufeff").strip()
        if not cleaned:
            return PortfolioState(portfolio_name=portfolio_name, source="csv_import", positions=[])

        # Detect delimiter (';' is standard for German bank CSV exports, ',' for international)
        first_line = cleaned.splitlines()[0]
        delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","

        reader = csv.DictReader(io.StringIO(cleaned), delimiter=delimiter)
        positions: List[Position] = []

        for row in reader:
            if not row:
                continue
            norm_row = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}

            ticker = (
                norm_row.get("ticker")
                or norm_row.get("symbol")
                or norm_row.get("kürzel")
                or norm_row.get("isin")
                or norm_row.get("wkn")
                or ""
            ).upper()
            if not ticker:
                continue

            quantity = parse_localized_float(
                norm_row.get("quantity")
                or norm_row.get("shares")
                or norm_row.get("stück")
                or norm_row.get("stueck")
                or norm_row.get("bestand")
                or norm_row.get("anzahl"),
                0.0,
            )
            if quantity <= 0:
                continue

            buy_in = parse_localized_float(
                norm_row.get("buy_in_price")
                or norm_row.get("buyin")
                or norm_row.get("einstandskurs")
                or norm_row.get("kaufkurs")
                or norm_row.get("averageprice")
                or norm_row.get("einstandspreis"),
                0.0,
            )
            current_price = parse_localized_float(
                norm_row.get("current_price")
                or norm_row.get("price")
                or norm_row.get("kurs")
                or norm_row.get("aktueller kurs"),
                buy_in,
            )
            name = (
                norm_row.get("name")
                or norm_row.get("bezeichnung")
                or norm_row.get("wertpapier")
                or norm_row.get("company")
                or ticker
            )
            isin = (norm_row.get("isin") or "").upper()
            currency = (norm_row.get("currency") or norm_row.get("währung") or "EUR").upper()
            raw_sector = norm_row.get("sector") or norm_row.get("branche") or ""
            raw_country = norm_row.get("country") or norm_row.get("land") or ""

            sector, country = self.taxonomy.classify_stock(
                ticker=ticker,
                raw_sector=raw_sector,
                raw_country=raw_country,
            )

            positions.append(
                Position(
                    ticker=ticker,
                    isin=isin,
                    name=name,
                    quantity=quantity,
                    buy_in_price=buy_in,
                    current_price=current_price if current_price > 0 else buy_in,
                    currency=currency,
                    sector=sector,
                    country=country,
                )
            )

        return PortfolioState(
            portfolio_name=portfolio_name,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            source="csv_import",
            positions=positions,
        )


class DemoPortfolioAdapter:
    """Loads the sample portfolio from data/mock_portfolio.json."""

    def __init__(
        self,
        store: Optional[JsonStore] = None,
        taxonomy: Optional[TaxonomyManager] = None,
    ) -> None:
        self.store = store or JsonStore()
        self.taxonomy = taxonomy or TaxonomyManager(self.store)

    def load_demo_portfolio(self) -> PortfolioState:
        """Read data/mock_portfolio.json and apply current taxonomy overrides."""
        raw = self.store.read_json("mock_portfolio.json", default={})
        if isinstance(raw, dict) and isinstance(raw.get("positions"), list):
            state = PortfolioState(**raw)
            for pos in state.positions:
                pos.sector, pos.country = self.taxonomy.classify_stock(
                    ticker=pos.ticker,
                    raw_sector=pos.sector,
                    raw_country=pos.country,
                )
            return state
        return PortfolioState(portfolio_name="Demo Portfolio", source="demo", positions=[])
