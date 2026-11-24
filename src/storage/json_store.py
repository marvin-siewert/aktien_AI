"""
Centralized JSON storage and TTL file cache manager.

Handles reading and writing of:
- Active and saved portfolio snapshots
- Saved buy theses (data/portfolio_thesis.json)
- Active and historical taxonomy versions (sectors, countries, overrides)
- Custom watchlist tickers
- Time-to-live (TTL) cached market data in data/cache/
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def sanitize_filename(name: str) -> str:
    """Convert an arbitrary user label into a safe filesystem filename segment."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name.strip())
    return cleaned.strip("_")[:50] or "snapshot"


class JsonStore:
    """Provides safe, atomic JSON persistence and file-based caching inside the data directory."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir: Path = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.cache_dir: Path = self.data_dir / "cache"
        self.taxonomy_history_dir: Path = self.data_dir / "taxonomy_history"
        self.portfolio_saved_dir: Path = self.data_dir / "portfolio_saved"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create required data and snapshot directories if they do not exist."""
        for folder in (
            self.data_dir,
            self.cache_dir,
            self.taxonomy_history_dir,
            self.portfolio_saved_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)

    def read_json(self, relative_or_abs_path: str | Path, default: Any = None) -> Any:
        """Read a JSON file from disk, returning `default` if the file does not exist or is invalid."""
        path = Path(relative_or_abs_path)
        if not path.is_absolute():
            path = self.data_dir / path
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return default

    def write_json(self, relative_or_abs_path: str | Path, payload: Any) -> Path:
        """Write a JSON-serializable payload to disk with UTF-8 encoding and clean indentation."""
        path = Path(relative_or_abs_path)
        if not path.is_absolute():
            path = self.data_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return path

    # -------------------------------------------------------------------------
    # Cache Management (TTL in seconds)
    # -------------------------------------------------------------------------
    def get_cache(self, cache_key: str, ttl_seconds: int = 86400) -> Optional[Any]:
        """Retrieve a cached object if it exists and has not expired."""
        safe_key = sanitize_filename(cache_key)
        cache_file = self.cache_dir / f"{safe_key}.json"
        if not cache_file.exists():
            return None
        try:
            with cache_file.open("r", encoding="utf-8") as fh:
                wrapper = json.load(fh)
            timestamp = float(wrapper.get("timestamp", 0))
            if (time.time() - timestamp) <= ttl_seconds:
                return wrapper.get("data")
        except (json.JSONDecodeError, OSError, ValueError):
            return None
        return None

    def set_cache(self, cache_key: str, data: Any) -> Path:
        """Store data in the local cache directory with the current Unix timestamp."""
        safe_key = sanitize_filename(cache_key)
        cache_file = self.cache_dir / f"{safe_key}.json"
        wrapper = {
            "timestamp": time.time(),
            "cached_at": datetime.now().isoformat(timespec="seconds"),
            "data": data,
        }
        return self.write_json(cache_file, wrapper)

    def clear_cache(self) -> int:
        """Delete all cached JSON files and return the count of removed files."""
        removed = 0
        for file_path in self.cache_dir.glob("*.json"):
            try:
                file_path.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    # -------------------------------------------------------------------------
    # Buy Thesis Persistence (data/portfolio_thesis.json)
    # -------------------------------------------------------------------------
    def load_theses(self) -> Dict[str, Dict[str, Any]]:
        """Load all saved buy theses keyed by ticker symbol."""
        raw = self.read_json("portfolio_thesis.json", default={"theses": {}})
        if isinstance(raw, dict) and "theses" in raw and isinstance(raw["theses"], dict):
            return raw["theses"]
        return {}

    def save_thesis(self, ticker: str, thesis_data: Dict[str, Any]) -> None:
        """Save or update a buy thesis for a specific ticker in data/portfolio_thesis.json."""
        theses = self.load_theses()
        theses[ticker.upper()] = thesis_data
        self.write_json("portfolio_thesis.json", {"theses": theses})

    def delete_thesis(self, ticker: str) -> bool:
        """Delete a stored buy thesis by ticker. Returns True if removed."""
        theses = self.load_theses()
        upper_ticker = ticker.upper()
        if upper_ticker in theses:
            del theses[upper_ticker]
            self.write_json("portfolio_thesis.json", {"theses": theses})
            return True
        return False

    # -------------------------------------------------------------------------
    # Custom Watchlist Persistence (data/custom_watchlist.json)
    # -------------------------------------------------------------------------
    def load_custom_watchlist(self) -> List[str]:
        """Return list of user-configured custom watchlist tickers."""
        raw = self.read_json("custom_watchlist.json", default={"tickers": []})
        tickers = raw.get("tickers", []) if isinstance(raw, dict) else []
        return [str(t).strip().upper() for t in tickers if str(t).strip()]

    def save_custom_watchlist(self, tickers: List[str]) -> None:
        """Save a cleaned list of custom watchlist tickers."""
        cleaned = sorted(list({str(t).strip().upper() for t in tickers if str(t).strip()}))
        self.write_json("custom_watchlist.json", {"tickers": cleaned})

    # -------------------------------------------------------------------------
    # Persistent App Settings (data/app_settings.json)
    # -------------------------------------------------------------------------
    def load_app_settings(self) -> Dict[str, Any]:
        """Load persisted user preferences such as the Scalable CLI executable path."""
        raw = self.read_json("app_settings.json", default={})
        return raw if isinstance(raw, dict) else {}

    def save_app_setting(self, key: str, value: Any) -> None:
        """Save or update a single persistent user preference in data/app_settings.json."""
        settings = self.load_app_settings()
        settings[key] = value
        self.write_json("app_settings.json", settings)
