"""
Taxonomy Manager for Sector ('Branchen') and Country ('Länder') Classification.

Provides:
- Default initial lists (13 sectors separating Software & Semiconductors, 12 countries/regions)
- Automatic mapping from raw yfinance sector/industry/country metadata
- Manual per-ticker overrides (user customizations take priority over auto-mapping)
- Version history (saving timestamped snapshots and restoring older list versions)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.models.entities import TaxonomyConfig
from src.storage.json_store import JsonStore, sanitize_filename


DEFAULT_SECTORS: List[str] = [
    "Technologie & Software",
    "Halbleiter & Hardware",
    "Gesundheit & Pharma",
    "Finanzen & Versicherungen",
    "Industrie & Maschinenbau",
    "Basiskonsumgüter",
    "Zyklischer Konsum & Handel",
    "Kommunikation & Medien",
    "Energie",
    "Grundstoffe & Chemie",
    "Immobilien (REITs)",
    "Versorger",
    "Sonstige / Unklassifiziert",
]

DEFAULT_COUNTRIES: List[str] = [
    "USA",
    "Deutschland",
    "Großbritannien",
    "Frankreich",
    "Schweiz",
    "Niederlande",
    "Skandinavien & Übriges Europa",
    "Japan",
    "China & Hongkong",
    "Kanada & Australien",
    "Schwellenländer (Emerging Markets)",
    "Sonstige / Global",
]

DEFAULT_SECTOR_MAPPING: Dict[str, str] = {
    "semiconductor": "Halbleiter & Hardware",
    "computer hardware": "Halbleiter & Hardware",
    "electronic components": "Halbleiter & Hardware",
    "communication equipment": "Halbleiter & Hardware",
    "consumer electronics": "Halbleiter & Hardware",
    "scientific & technical instruments": "Halbleiter & Hardware",
    "technology": "Technologie & Software",
    "software": "Technologie & Software",
    "information technology": "Technologie & Software",
    "it services": "Technologie & Software",
    "healthcare": "Gesundheit & Pharma",
    "biotechnology": "Gesundheit & Pharma",
    "drug manufacturers": "Gesundheit & Pharma",
    "medical": "Gesundheit & Pharma",
    "financial services": "Finanzen & Versicherungen",
    "financial": "Finanzen & Versicherungen",
    "banks": "Finanzen & Versicherungen",
    "insurance": "Finanzen & Versicherungen",
    "capital markets": "Finanzen & Versicherungen",
    "industrials": "Industrie & Maschinenbau",
    "aerospace & defense": "Industrie & Maschinenbau",
    "machinery": "Industrie & Maschinenbau",
    "consumer defensive": "Basiskonsumgüter",
    "consumer staples": "Basiskonsumgüter",
    "household": "Basiskonsumgüter",
    "beverages": "Basiskonsumgüter",
    "packaged foods": "Basiskonsumgüter",
    "consumer cyclical": "Zyklischer Konsum & Handel",
    "consumer discretionary": "Zyklischer Konsum & Handel",
    "internet retail": "Zyklischer Konsum & Handel",
    "auto manufacturers": "Zyklischer Konsum & Handel",
    "communication services": "Kommunikation & Medien",
    "telecom": "Kommunikation & Medien",
    "entertainment": "Kommunikation & Medien",
    "internet content": "Kommunikation & Medien",
    "energy": "Energie",
    "oil & gas": "Energie",
    "solar": "Energie",
    "basic materials": "Grundstoffe & Chemie",
    "chemicals": "Grundstoffe & Chemie",
    "metals & mining": "Grundstoffe & Chemie",
    "real estate": "Immobilien (REITs)",
    "reit": "Immobilien (REITs)",
    "utilities": "Versorger",
}

DEFAULT_COUNTRY_MAPPING: Dict[str, str] = {
    "united states": "USA",
    "usa": "USA",
    "us": "USA",
    "germany": "Deutschland",
    "deutschland": "Deutschland",
    "united kingdom": "Großbritannien",
    "uk": "Großbritannien",
    "great britain": "Großbritannien",
    "france": "Frankreich",
    "switzerland": "Schweiz",
    "netherlands": "Niederlande",
    "denmark": "Skandinavien & Übriges Europa",
    "sweden": "Skandinavien & Übriges Europa",
    "norway": "Skandinavien & Übriges Europa",
    "finland": "Skandinavien & Übriges Europa",
    "ireland": "Skandinavien & Übriges Europa",
    "italy": "Skandinavien & Übriges Europa",
    "spain": "Skandinavien & Übriges Europa",
    "belgium": "Skandinavien & Übriges Europa",
    "austria": "Skandinavien & Übriges Europa",
    "japan": "Japan",
    "china": "China & Hongkong",
    "hong kong": "China & Hongkong",
    "canada": "Kanada & Australien",
    "australia": "Kanada & Australien",
    "taiwan": "Schwellenländer (Emerging Markets)",
    "india": "Schwellenländer (Emerging Markets)",
    "brazil": "Schwellenländer (Emerging Markets)",
    "south korea": "Schwellenländer (Emerging Markets)",
    "mexico": "Schwellenländer (Emerging Markets)",
}


def create_default_taxonomy() -> TaxonomyConfig:
    """Create a fresh default TaxonomyConfig with the recommended 13 sectors and 12 countries."""
    return TaxonomyConfig(
        version_label="Standard-Startliste (GICS + Halbleiter)",
        updated_at=datetime.now().isoformat(timespec="seconds"),
        sectors=list(DEFAULT_SECTORS),
        countries=list(DEFAULT_COUNTRIES),
        sector_mapping=dict(DEFAULT_SECTOR_MAPPING),
        country_mapping=dict(DEFAULT_COUNTRY_MAPPING),
        ticker_overrides={
            "NVDA": {"sector": "Halbleiter & Hardware", "country": "USA"},
            "AAPL": {"sector": "Halbleiter & Hardware", "country": "USA"},
            "ASML.AS": {"sector": "Halbleiter & Hardware", "country": "Niederlande"},
            "IFX.DE": {"sector": "Halbleiter & Hardware", "country": "Deutschland"},
        },
    )


class TaxonomyManager:
    """
    Manages sector and country classification lists, automatic mapping, per-stock overrides,
    and historical version snapshots.
    """

    ACTIVE_FILE = "taxonomy_active.json"

    def __init__(self, store: Optional[JsonStore] = None) -> None:
        self.store = store or JsonStore()
        self.config: TaxonomyConfig = self.load_active()

    def load_active(self) -> TaxonomyConfig:
        """Load the active taxonomy configuration from disk, initializing defaults if missing."""
        raw = self.store.read_json(self.ACTIVE_FILE)
        if not raw or not isinstance(raw, dict):
            default_cfg = create_default_taxonomy()
            self.store.write_json(self.ACTIVE_FILE, default_cfg.model_dump())
            return default_cfg
        try:
            cfg = TaxonomyConfig(**raw)
            if not cfg.sectors:
                cfg.sectors = list(DEFAULT_SECTORS)
            if not cfg.countries:
                cfg.countries = list(DEFAULT_COUNTRIES)
            return cfg
        except Exception:
            default_cfg = create_default_taxonomy()
            self.store.write_json(self.ACTIVE_FILE, default_cfg.model_dump())
            return default_cfg

    def save_active(self, create_snapshot: bool = True, version_label: Optional[str] = None) -> Optional[Path]:
        """
        Save the current taxonomy configuration as active and optionally archive a snapshot
        in data/taxonomy_history/ so older lists can always be restored.
        """
        self.config.updated_at = datetime.now().isoformat(timespec="seconds")
        if version_label:
            self.config.version_label = version_label.strip()

        payload = self.config.model_dump()
        self.store.write_json(self.ACTIVE_FILE, payload)

        if create_snapshot:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_label = sanitize_filename(self.config.version_label)
            snapshot_name = f"taxonomy_{ts}_{safe_label}.json"
            snapshot_path = self.store.taxonomy_history_dir / snapshot_name
            return self.store.write_json(snapshot_path, payload)
        return None

    def classify_stock(
        self,
        ticker: str,
        raw_sector: str = "",
        raw_industry: str = "",
        raw_country: str = "",
    ) -> Tuple[str, str]:
        """
        Determine the assigned (sector, country) for a given ticker.
        1. Checks manual ticker_overrides first.
        2. Applies keyword matching against raw_industry and raw_sector.
        3. Applies keyword matching against raw_country (and ticker suffix heuristics like .DE).
        4. Falls back to the last entry in the active sectors/countries list ('Sonstige').
        """
        upper_ticker = ticker.strip().upper()
        fallback_sector = self.config.sectors[-1] if self.config.sectors else "Sonstige / Unklassifiziert"
        fallback_country = self.config.countries[-1] if self.config.countries else "Sonstige / Global"

        override = self.config.ticker_overrides.get(upper_ticker, {})
        override_sector = override.get("sector")
        override_country = override.get("country")

        # 1. Resolve Sector
        assigned_sector = ""
        if override_sector and override_sector in self.config.sectors:
            assigned_sector = override_sector
        else:
            # Check direct match in user sectors first
            for candidate_raw in (raw_industry, raw_sector):
                if candidate_raw in self.config.sectors:
                    assigned_sector = candidate_raw
                    break

            if not assigned_sector:
                combined_raw = f"{raw_industry} {raw_sector}".lower()
                # Check industry keywords first (so 'semiconductor' wins over generic 'technology')
                for keyword, mapped_sector in self.config.sector_mapping.items():
                    if keyword.lower() in combined_raw and mapped_sector in self.config.sectors:
                        assigned_sector = mapped_sector
                        break

        if not assigned_sector:
            assigned_sector = fallback_sector

        # 2. Resolve Country
        assigned_country = ""
        if override_country and override_country in self.config.countries:
            assigned_country = override_country
        else:
            if raw_country in self.config.countries:
                assigned_country = raw_country
            elif raw_country:
                raw_country_lower = raw_country.strip().lower()
                for keyword, mapped_country in self.config.country_mapping.items():
                    if keyword.lower() == raw_country_lower or keyword.lower() in raw_country_lower:
                        if mapped_country in self.config.countries:
                            assigned_country = mapped_country
                            break

            # Heuristic fallback by ticker exchange suffix if raw_country was empty
            if not assigned_country:
                assigned_country = self._infer_country_from_ticker(upper_ticker, fallback_country)

        return assigned_sector, assigned_country

    def _infer_country_from_ticker(self, upper_ticker: str, fallback_country: str) -> str:
        """Infer country from common Yahoo Finance exchange suffixes when metadata is unavailable."""
        suffix_map = {
            ".DE": "Deutschland",
            ".F": "Deutschland",
            ".L": "Großbritannien",
            ".PA": "Frankreich",
            ".SW": "Schweiz",
            ".AS": "Niederlande",
            ".CO": "Skandinavien & Übriges Europa",
            ".ST": "Skandinavien & Übriges Europa",
            ".OL": "Skandinavien & Übriges Europa",
            ".HE": "Skandinavien & Übriges Europa",
            ".MI": "Skandinavien & Übriges Europa",
            ".MC": "Skandinavien & Übriges Europa",
            ".T": "Japan",
            ".HK": "China & Hongkong",
            ".TO": "Kanada & Australien",
            ".AX": "Kanada & Australien",
        }
        for suffix, country_name in suffix_map.items():
            if upper_ticker.endswith(suffix) and country_name in self.config.countries:
                return country_name
        # Plain tickers without dot suffix on Yahoo Finance are typically US-listed
        if "." not in upper_ticker and "USA" in self.config.countries:
            return "USA"
        return fallback_country

    def set_ticker_override(
        self,
        ticker: str,
        sector: Optional[str] = None,
        country: Optional[str] = None,
        persist: bool = True,
    ) -> None:
        """Set or update a manual sector/country override for a specific stock ticker."""
        upper_ticker = ticker.strip().upper()
        if not upper_ticker:
            return
        entry = dict(self.config.ticker_overrides.get(upper_ticker, {}))
        if sector and sector in self.config.sectors:
            entry["sector"] = sector
        if country and country in self.config.countries:
            entry["country"] = country
        self.config.ticker_overrides[upper_ticker] = entry
        if persist:
            self.save_active(create_snapshot=False)

    def remove_ticker_override(self, ticker: str, persist: bool = True) -> bool:
        """Remove a manual override for a ticker so it reverts to automatic classification."""
        upper_ticker = ticker.strip().upper()
        if upper_ticker in self.config.ticker_overrides:
            del self.config.ticker_overrides[upper_ticker]
            if persist:
                self.save_active(create_snapshot=False)
            return True
        return False

    def update_lists(
        self,
        new_sectors: List[str],
        new_countries: List[str],
        version_label: str = "Benutzerdefinierte Liste",
        create_snapshot: bool = True,
    ) -> Optional[Path]:
        """
        Update the active sector and country lists (cleaning whitespace & duplicates)
        and save a snapshot in the history directory.
        """
        cleaned_sectors = [s.strip() for s in new_sectors if s.strip()]
        cleaned_countries = [c.strip() for c in new_countries if c.strip()]

        # Deduplicate while preserving order
        seen_s: set[str] = set()
        unique_sectors = [s for s in cleaned_sectors if not (s in seen_s or seen_s.add(s))]
        seen_c: set[str] = set()
        unique_countries = [c for c in cleaned_countries if not (c in seen_c or seen_c.add(c))]

        if not unique_sectors:
            unique_sectors = list(DEFAULT_SECTORS)
        if not unique_countries:
            unique_countries = list(DEFAULT_COUNTRIES)

        self.config.sectors = unique_sectors
        self.config.countries = unique_countries
        return self.save_active(create_snapshot=create_snapshot, version_label=version_label)

    def list_history_snapshots(self) -> List[Dict[str, str]]:
        """
        List all saved historical taxonomy snapshots in reverse chronological order.
        Returns metadata dicts with keys: 'filename', 'version_label', 'updated_at', 'summary'.
        """
        snapshots: List[Dict[str, str]] = []
        files = sorted(self.store.taxonomy_history_dir.glob("taxonomy_*.json"), reverse=True)
        for file_path in files:
            raw = self.store.read_json(file_path)
            if isinstance(raw, dict):
                label = str(raw.get("version_label", file_path.stem))
                updated = str(raw.get("updated_at", ""))
                n_sec = len(raw.get("sectors", []))
                n_cnt = len(raw.get("countries", []))
                n_ovr = len(raw.get("ticker_overrides", {}))
                snapshots.append(
                    {
                        "filename": file_path.name,
                        "version_label": label,
                        "updated_at": updated,
                        "summary": f"{label} ({updated}) — {n_sec} Branchen, {n_cnt} Länder, {n_ovr} Overrides",
                    }
                )
        return snapshots

    def restore_snapshot(self, filename: str, backup_current: bool = True) -> TaxonomyConfig:
        """
        Restore a historical taxonomy configuration from data/taxonomy_history/<filename>.
        Automatically saves a backup of the current active state before restoring.
        """
        target_path = self.store.taxonomy_history_dir / filename
        raw = self.store.read_json(target_path)
        if not raw or not isinstance(raw, dict):
            raise FileNotFoundError(f"Taxonomy snapshot '{filename}' not found or invalid.")

        if backup_current:
            self.save_active(
                create_snapshot=True,
                version_label=f"Auto-Backup before restore ({self.config.version_label})",
            )

        self.config = TaxonomyConfig(**raw)
        self.save_active(create_snapshot=False)
        return self.config

    def reset_to_defaults(self, backup_current: bool = True) -> TaxonomyConfig:
        """Reset active taxonomy lists to the initial recommended defaults."""
        if backup_current:
            self.save_active(
                create_snapshot=True,
                version_label=f"Auto-Backup before reset ({self.config.version_label})",
            )
        self.config = create_default_taxonomy()
        self.save_active(create_snapshot=True, version_label="Reset to Standard Defaults")
        return self.config
