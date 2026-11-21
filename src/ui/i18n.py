"""
Internationalization (i18n) Manager for multi-language GUI support.

Supports instant switching between German ('de') and English ('en') via button,
and automatically discovers any new `locales/<lang>.json` files added in the future.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_LOCALES_DIR = Path(__file__).resolve().parent.parent.parent / "locales"

LANGUAGE_LABELS: Dict[str, str] = {
    "de": "🇩🇪 Deutsch",
    "en": "🇬🇧 English",
}


class I18nManager:
    """Loads translation dictionaries from `locales/*.json` and resolves UI text keys."""

    def __init__(self, lang: str = "de", locales_dir: Optional[Path] = None) -> None:
        self.locales_dir = Path(locales_dir) if locales_dir else DEFAULT_LOCALES_DIR
        self.lang = lang.lower().strip() if lang else "de"
        self._translations: Dict[str, Dict[str, str]] = {}
        self._load_all_locales()

    def _load_all_locales(self) -> None:
        """Load all JSON locale files from the locales directory."""
        if not self.locales_dir.exists():
            return
        for file_path in sorted(self.locales_dir.glob("*.json")):
            code = file_path.stem.lower()
            try:
                with file_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    self._translations[code] = {str(k): str(v) for k, v in data.items()}
            except (json.JSONDecodeError, OSError):
                continue

    def available_languages(self) -> List[str]:
        """Return list of available language codes (e.g. ['de', 'en'])."""
        codes = list(self._translations.keys())
        return codes if codes else ["de", "en"]

    def set_language(self, lang: str) -> None:
        """Switch active UI language code."""
        code = lang.lower().strip()
        if code in self._translations:
            self.lang = code

    def t(self, key: str, default: Optional[str] = None) -> str:
        """Translate a UI key into the currently active language with fallback to English or key name."""
        lang_dict = self._translations.get(self.lang, {})
        if key in lang_dict:
            return lang_dict[key]
        fallback_dict = self._translations.get("de", self._translations.get("en", {}))
        if key in fallback_dict:
            return fallback_dict[key]
        return default if default is not None else key
