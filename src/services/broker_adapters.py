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
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
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
        self.cli_cmd = (cli_cmd or os.getenv("SCALABLE_CLI_CMD", "") or "sc").strip()
        self.store = store or JsonStore()
        self.taxonomy = taxonomy or TaxonomyManager(self.store)

    def resolve_executable(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve the Scalable CLI executable safely on Windows & Unix.
        Prevents accidental execution of Windows Service Control Manager (`C:\\Windows\\System32\\sc.exe`).
        Returns (resolved_path_or_cmd, error_message).
        """
        candidate = self.cli_cmd.strip().strip('"')
        # Check common user-local installation paths on Windows if default 'sc' is used
        if candidate.lower() in ("sc", "sc.exe"):
            local_candidates = [
                Path("C:/Tools/scalable-cli/target/release/sc.exe"),
                Path.home() / ".cargo" / "bin" / "sc.exe",
                Path.home() / "scoop" / "shims" / "sc.exe",
                Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "scalable-cli" / "sc.exe",
                Path(os.getenv("LOCALAPPDATA", "")) / "scalable-cli" / "sc.exe",
            ]
            for loc in local_candidates:
                if loc.exists() and loc.is_file():
                    return str(loc), None

        resolved = shutil.which(candidate) if not Path(candidate).exists() else str(Path(candidate))
        if not resolved:
            return None, (
                f"Scalable CLI ('{candidate}') nicht gefunden. Bitte Pfad zur sc.exe angeben oder installieren."
            )

        norm_resolved = resolved.replace("/", "\\").lower()
        if norm_resolved.endswith("\\windows\\system32\\sc.exe") or norm_resolved.endswith("\\windows\\syswow64\\sc.exe"):
            return None, (
                "Windows-Konflikt erkannt: 'sc' zeigt auf C:\\Windows\\System32\\sc.exe (Windows-Dienstverwaltung) "
                "statt auf die Scalable Capital CLI. Bitte installiere 'scalable-cli' und gib den Pfad zur "
                "Scalable sc.exe (z. B. C:\\Users\\...\\.cargo\\bin\\sc.exe) an."
            )
        return resolved, None

    def _build_cmd(self, exe_args: List[str]) -> Tuple[Optional[List[str]], Optional[str]]:
        """Build subprocess command list, supporting both native sc.exe and WSL prefixes like 'wsl sc'."""
        candidate = self.cli_cmd.strip()
        if candidate.lower().startswith("wsl "):
            parts = candidate.split()
            return parts + exe_args, None
        exe_path, err = self.resolve_executable()
        if err or not exe_path:
            return None, err
        return [exe_path] + exe_args, None

    def _subprocess_env(self) -> Dict[str, str]:
        """Ensure HOME is populated on Windows so scalable-cli can resolve its default config path."""
        env = os.environ.copy()
        if not env.get("HOME"):
            env["HOME"] = env.get("USERPROFILE") or str(Path.home())
        return env

    def check_connection_status(self) -> Tuple[bool, str]:
        """Run `sc whoami` in read-only mode to verify CLI installation and active login session."""
        cmd, err = self._build_cmd(["whoami"])
        if err or not cmd:
            return False, err or "Scalable CLI nicht gefunden."
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=self._subprocess_env(),
            )
            out = (proc.stdout or proc.stderr or "").strip()
            if proc.returncode == 0 and out:
                return True, f"Verbunden ({' '.join(cmd[:-1])}): {out}"
            return False, f"Nicht eingeloggt. Bitte im Terminal '{' '.join(cmd[:-1])} login --local-read-only' ausführen. ({out})"
        except Exception as exc:
            return False, f"CLI-Prüfung fehlgeschlagen: {exc}"

    def fetch_portfolio(self, fallback_to_mock: bool = True) -> Tuple[PortfolioState, str]:
        """
        Execute `sc broker holdings --json` in read-only mode.
        Returns (PortfolioState, status_message).
        If the CLI is not installed or not logged in, falls back to mock_portfolio.json when enabled.
        """
        cmd, err = self._build_cmd(["broker", "holdings", "--json"])
        if err or not cmd:
            error_detail = err or "Scalable CLI not found."
        else:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                    env=self._subprocess_env(),
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
                        return state, f"Erfolgreich {len(positions)} Positionen von Scalable Capital CLI importiert!"
                error_detail = (proc.stderr or proc.stdout or "Keine Positionen oder nicht eingeloggt").strip()
            except subprocess.TimeoutExpired:
                error_detail = "Scalable CLI Zeitüberschreitung (20s)."
            except Exception as exc:
                error_detail = str(exc)

        if fallback_to_mock:
            demo_state = DemoPortfolioAdapter(self.store, self.taxonomy).load_demo_portfolio()
            return (
                demo_state,
                f"Scalable CLI nicht bereit ({error_detail}). Demo-Depot als Fallback geladen.",
            )

        raise RuntimeError(f"Scalable CLI Import fehlgeschlagen: {error_detail}")

    def _resolve_ticker_and_meta_from_isin(
        self, isin: str, fallback_name: str = ""
    ) -> Tuple[str, str, str]:
        """Resolve (ticker, raw_sector, raw_industry) from an ISIN via Yahoo Finance search."""
        clean_isin = isin.strip().upper()
        if not clean_isin:
            return fallback_name.strip().upper(), "", ""

        cache_key = f"isin_meta_{clean_isin}"
        cached = self.store.get_cache(cache_key, ttl_seconds=30 * 86400)
        if isinstance(cached, dict) and cached.get("symbol"):
            return (
                str(cached["symbol"]).upper(),
                str(cached.get("sector") or ""),
                str(cached.get("industry") or ""),
            )

        # Support legacy string cache key from earlier version
        legacy_cached = self.store.get_cache(f"isin_ticker_{clean_isin}", ttl_seconds=30 * 86400)
        if isinstance(legacy_cached, str) and legacy_cached.strip():
            return legacy_cached.strip().upper(), "", ""

        try:
            import yfinance as yf

            search_res = yf.Search(clean_isin, max_results=5)
            quotes = getattr(search_res, "quotes", []) or []
            if quotes:
                chosen = next(
                    (
                        q for q in quotes
                        if str(q.get("symbol") or "").strip()
                        and str(q.get("quoteType") or "").upper() in ("EQUITY", "ETF", "")
                    ),
                    quotes[0],
                )
                sym = str(chosen.get("symbol") or "").strip().upper()
                sec = str(chosen.get("sector") or "").strip()
                ind = str(chosen.get("industry") or "").strip()
                if sym:
                    self.store.set_cache(cache_key, {"symbol": sym, "sector": sec, "industry": ind})
                    return sym, sec, ind
        except Exception:
            pass

        return clean_isin, "", ""

    def parse_cli_json(self, raw_json: str) -> List[Position]:
        """
        Parse the JSON output of `sc broker holdings --json`.
        Handles `scalable-cli v1.3+` envelope (`data.result.items` & `data.result.crypto_items`)
        as well as legacy list/`holdings`/`positions` envelopes.
        """
        payload = json.loads(raw_json)
        items: List[Dict[str, Any]] = []
        crypto_items: List[Dict[str, Any]] = []

        if isinstance(payload, list):
            items = [x for x in payload if isinstance(x, dict)]
        elif isinstance(payload, dict):
            if isinstance(payload.get("data"), dict):
                data_obj = payload["data"]
                if isinstance(data_obj.get("result"), dict):
                    res_obj = data_obj["result"]
                    items = res_obj.get("items") or res_obj.get("holdings") or res_obj.get("positions") or []
                    crypto_items = res_obj.get("crypto_items") or []
                else:
                    items = data_obj.get("holdings") or data_obj.get("positions") or data_obj.get("items") or []
            elif isinstance(payload.get("holdings"), list):
                items = payload["holdings"]
            elif isinstance(payload.get("positions"), list):
                items = payload["positions"]
            elif isinstance(payload.get("data"), list):
                items = payload["data"]

        positions: List[Position] = []
        for item in items:
            isin = str(item.get("isin") or "").strip().upper()
            raw_ticker = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
            name = str(item.get("name") or item.get("title") or raw_ticker or isin).strip()

            raw_sector = str(item.get("sector") or "")
            raw_industry = str(item.get("industry") or "")
            raw_country = str(item.get("country") or "")

            if raw_ticker:
                ticker = raw_ticker
            else:
                ticker, resolved_sec, resolved_ind = self._resolve_ticker_and_meta_from_isin(
                    isin, fallback_name=name
                )
                if not raw_sector:
                    raw_sector = resolved_sec
                if not raw_industry:
                    raw_industry = resolved_ind
            if not ticker:
                continue

            quantity = parse_localized_float(
                item.get("quantity") or item.get("shares") or item.get("amount"), 0.0
            )
            if quantity <= 0:
                continue

            buy_in = parse_localized_float(
                item.get("fifo_price")
                or item.get("averagePrice")
                or item.get("buyInPrice")
                or item.get("buy_in_price")
                or item.get("purchasePrice"),
                0.0,
            )
            current_price = parse_localized_float(
                item.get("quote_mid_price")
                or item.get("currentPrice")
                or item.get("price")
                or item.get("lastPrice")
                or item.get("current_price"),
                buy_in,
            )
            currency = str(
                item.get("quote_currency")
                or item.get("valuation_currency")
                or item.get("currency")
                or "EUR"
            ).strip().upper()
            sector, country = self.taxonomy.classify_stock(
                ticker=ticker,
                raw_sector=raw_sector,
                raw_industry=raw_industry,
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

        # Also include any actually held crypto positions (filled > 0)
        for c_item in crypto_items:
            pos_obj = c_item.get("position") or {}
            qty = parse_localized_float(pos_obj.get("filled"), 0.0) if isinstance(pos_obj, dict) else 0.0
            if qty <= 0:
                continue
            c_ticker = str(c_item.get("ticker") or "").strip().upper()
            if not c_ticker:
                continue
            positions.append(
                Position(
                    ticker=f"{c_ticker}-USD",
                    name=str(c_item.get("name") or c_ticker),
                    quantity=qty,
                    buy_in_price=0.0,
                    current_price=0.0,
                    currency="EUR",
                    sector=self.taxonomy.config.sectors[-1],
                    country=self.taxonomy.config.countries[-1],
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
