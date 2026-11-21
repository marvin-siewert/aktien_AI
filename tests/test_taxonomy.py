"""
Unit tests for Sector ('Branchen') & Country ('Länder') TaxonomyManager.

Tests:
- Default 13 sectors and 12 countries initialization
- Automatic mapping of raw yfinance sector/industry/country metadata
- Manual per-stock overrides taking precedence over automatic mapping
- Updating lists, saving historical snapshots, and restoring older versions
"""

from __future__ import annotations

from src.core.taxonomy_manager import DEFAULT_COUNTRIES, DEFAULT_SECTORS, TaxonomyManager


def test_default_taxonomy_lists(temp_taxonomy: TaxonomyManager) -> None:
    """Verify initial sector and country lists match the recommended defaults."""
    assert len(temp_taxonomy.config.sectors) == len(DEFAULT_SECTORS)
    assert "Technologie & Software" in temp_taxonomy.config.sectors
    assert "Halbleiter & Hardware" in temp_taxonomy.config.sectors
    assert len(temp_taxonomy.config.countries) == len(DEFAULT_COUNTRIES)
    assert "Deutschland" in temp_taxonomy.config.countries
    assert "USA" in temp_taxonomy.config.countries


def test_automatic_classification_and_semiconductor_split(temp_taxonomy: TaxonomyManager) -> None:
    """Verify automatic mapping separates Semiconductors from generic Software/Technology."""
    sec_chip, cnt_chip = temp_taxonomy.classify_stock(
        ticker="AMD",
        raw_sector="Technology",
        raw_industry="Semiconductors",
        raw_country="United States",
    )
    assert sec_chip == "Halbleiter & Hardware"
    assert cnt_chip == "USA"

    sec_soft, cnt_soft = temp_taxonomy.classify_stock(
        ticker="SAP.DE",
        raw_sector="Technology",
        raw_industry="Software - Application",
        raw_country="Germany",
    )
    assert sec_soft == "Technologie & Software"
    assert cnt_soft == "Deutschland"


def test_manual_ticker_override_takes_precedence(temp_taxonomy: TaxonomyManager) -> None:
    """Verify user-defined per-stock override beats automatic yfinance mapping."""
    temp_taxonomy.set_ticker_override(
        ticker="AMZN",
        sector="Technologie & Software",
        country="USA",
    )
    sec, cnt = temp_taxonomy.classify_stock(
        ticker="AMZN",
        raw_sector="Consumer Cyclical",
        raw_industry="Internet Retail",
        raw_country="United States",
    )
    assert sec == "Technologie & Software"
    assert cnt == "USA"

    # Removing the override reverts to automatic classification
    assert temp_taxonomy.remove_ticker_override("AMZN") is True
    sec_reverted, _ = temp_taxonomy.classify_stock(
        ticker="AMZN",
        raw_sector="Consumer Cyclical",
        raw_industry="Internet Retail",
        raw_country="United States",
    )
    assert sec_reverted == "Zyklischer Konsum & Handel"


def test_taxonomy_version_history_save_and_restore(temp_taxonomy: TaxonomyManager) -> None:
    """Verify saving custom lists creates a historical snapshot and older versions can be restored."""
    # Save version 1
    custom_sectors_v1 = ["Tech & KI", "Medizin", "Sonstige"]
    custom_countries_v1 = ["USA", "Europa", "Global"]
    snap_v1 = temp_taxonomy.update_lists(
        new_sectors=custom_sectors_v1,
        new_countries=custom_countries_v1,
        version_label="Version 1 Kompakt",
        create_snapshot=True,
    )
    assert snap_v1 is not None and snap_v1.exists()
    assert temp_taxonomy.config.sectors == custom_sectors_v1

    # Save version 2
    custom_sectors_v2 = ["Tech & KI", "Medizin", "Energie & Klima", "Sonstige"]
    temp_taxonomy.update_lists(
        new_sectors=custom_sectors_v2,
        new_countries=custom_countries_v1,
        version_label="Version 2 Erweitert",
        create_snapshot=True,
    )
    assert len(temp_taxonomy.config.sectors) == 4

    # Check snapshot history listing
    snapshots = temp_taxonomy.list_history_snapshots()
    assert len(snapshots) >= 2

    # Restore Version 1
    restored = temp_taxonomy.restore_snapshot(snap_v1.name, backup_current=True)
    assert restored.sectors == custom_sectors_v1
    assert restored.version_label == "Version 1 Kompakt"
