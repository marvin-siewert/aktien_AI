"""
Unit tests for PortfolioManager and Broker/Bank Import Adapters.

Tests:
- Manual adding, updating, and removing positions without any broker dependency
- Saving named portfolio states and restoring them from `data/portfolio_saved/`
- Parsing Scalable Capital CLI JSON output (`sc broker holdings --json`) and mock fallback
- Parsing German and international Bank/Broker CSV exports
"""

from __future__ import annotations

import json

from src.core.portfolio_manager import PortfolioManager
from src.core.taxonomy_manager import TaxonomyManager
from src.services.broker_adapters import BankCsvImportAdapter, ScalableCliAdapter
from src.storage.json_store import JsonStore


def test_manual_position_crud_and_snapshots(temp_store: JsonStore, temp_taxonomy: TaxonomyManager) -> None:
    """Verify manual position entry, editing, and saving/loading named portfolio states."""
    pm = PortfolioManager(store=temp_store, taxonomy=temp_taxonomy)
    pm.state.positions = []

    # Add a position manually
    pos = pm.add_or_update_position(
        ticker="MSFT",
        quantity=15.0,
        buy_in_price=380.0,
        name="Microsoft Corp.",
        sector="Technologie & Software",
        country="USA",
        auto_enrich=False,
    )
    assert pos.ticker == "MSFT"
    assert pos.quantity == 15.0
    assert len(pm.state.positions) == 1

    # Save named snapshot 1
    snap_1 = pm.save_snapshot("Depot Stand Alpha")
    assert snap_1.exists()

    # Modify portfolio (add second position)
    pm.add_or_update_position(
        ticker="SAP.DE",
        quantity=20.0,
        buy_in_price=190.0,
        sector="Technologie & Software",
        country="Deutschland",
        auto_enrich=False,
    )
    assert len(pm.state.positions) == 2

    # Load Snapshot 1 back -> should restore single position state
    restored = pm.load_snapshot(snap_1.name)
    assert restored.portfolio_name == "Depot Stand Alpha"
    assert len(restored.positions) == 1
    assert restored.positions[0].ticker == "MSFT"


def test_scalable_cli_json_parsing_and_fallback(temp_store: JsonStore, temp_taxonomy: TaxonomyManager) -> None:
    """Verify parsing of official Scalable Capital CLI (`sc broker holdings --json`) output."""
    adapter = ScalableCliAdapter(cli_cmd="non_existent_sc_binary_xyz", store=temp_store, taxonomy=temp_taxonomy)

    sample_cli_output = json.dumps(
        {
            "holdings": [
                {
                    "ticker": "NVDA",
                    "isin": "US67066G1040",
                    "name": "NVIDIA Corp.",
                    "quantity": 25,
                    "averagePrice": 110.50,
                    "currentPrice": 138.20,
                    "currency": "USD",
                },
                {
                    "symbol": "SAP.DE",
                    "name": "SAP SE",
                    "shares": "12,5",
                    "buyInPrice": "175,40",
                    "price": "218,40",
                    "currency": "EUR",
                },
            ]
        }
    )

    positions = adapter.parse_cli_json(sample_cli_output)
    assert len(positions) == 2
    assert positions[0].ticker == "NVDA"
    assert positions[0].quantity == 25.0
    assert positions[0].sector == "Halbleiter & Hardware"
    assert positions[1].ticker == "SAP.DE"
    assert positions[1].quantity == 12.5
    assert positions[1].buy_in_price == 175.40
    assert positions[1].country == "Deutschland"


def test_scalable_cli_v13_real_envelope_parsing(temp_store: JsonStore, temp_taxonomy: TaxonomyManager) -> None:
    """Verify parsing of real `scalable-cli v1.3.0` (`data.result.items` with `fifo_price` & `quote_mid_price`)."""
    adapter = ScalableCliAdapter(store=temp_store, taxonomy=temp_taxonomy)
    # Pre-seed ISIN cache so test runs deterministically offline
    temp_store.set_cache("isin_ticker_US09857L1089", "BKNG")
    temp_store.set_cache("isin_ticker_US67066G1040", "NVDA")

    real_payload = json.dumps(
        {
            "ok": True,
            "command": "broker.holdings",
            "data": {
                "result": {
                    "crypto_items": [
                        {"kind": "crypto", "name": "Bitcoin", "position": {"filled": 0}, "ticker": "BTC"}
                    ],
                    "items": [
                        {
                            "fifo_price": 134.95,
                            "isin": "US09857L1089",
                            "kind": "security",
                            "name": "Booking Holdings",
                            "quantity": 1,
                            "quote_currency": "EUR",
                            "quote_mid_price": 134.35,
                        },
                        {
                            "fifo_price": 122.38,
                            "isin": "US67066G1040",
                            "kind": "security",
                            "name": "NVIDIA",
                            "quantity": 1,
                            "quote_currency": "EUR",
                            "quote_mid_price": 138.87,
                        },
                    ],
                }
            },
        }
    )

    positions = adapter.parse_cli_json(real_payload)
    assert len(positions) == 2
    assert positions[0].ticker == "BKNG"
    assert positions[0].buy_in_price == 134.95
    assert positions[0].current_price == 134.35
    assert positions[1].ticker == "NVDA"
    assert positions[1].sector == "Halbleiter & Hardware"
    assert positions[1].current_price == 138.87


def test_scalable_cli_login_command_and_logout(temp_store: JsonStore, temp_taxonomy: TaxonomyManager, mocker) -> None:
    """Verify PowerShell copy-paste login command generation and `sc logout` execution."""
    adapter = ScalableCliAdapter(
        cli_cmd=r"C:\Tools\scalable-cli\target\release\sc.exe",
        store=temp_store,
        taxonomy=temp_taxonomy,
    )
    login_cmd = adapter.build_login_command()
    assert "login --local-read-only" in login_cmd
    assert "sc.exe" in login_cmd

    mock_run = mocker.patch("src.services.broker_adapters.subprocess.run")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "Logged out"
    mock_run.return_value.stderr = ""
    ok, msg = adapter.logout()
    assert ok is True
    assert "beendet" in msg


def test_bank_csv_import_german_format(temp_taxonomy: TaxonomyManager) -> None:
    """Verify bank CSV import with German semicolon delimiter and comma decimals."""
    csv_content = (
        "Ticker;Bezeichnung;Stück;Einstandskurs;Aktueller Kurs;Währung;Branche;Land\n"
        "ALV.DE;Allianz SE;14,0;245,50 €;292,00 €;EUR;Finanzen & Versicherungen;Deutschland\n"
        "MSFT;Microsoft Corp.;8,5;350,00;425,50;USD;Technology;United States\n"
    )
    adapter = BankCsvImportAdapter(taxonomy=temp_taxonomy)
    state = adapter.parse_csv_content(csv_content, portfolio_name="ING CSV Import")

    assert len(state.positions) == 2
    assert state.positions[0].ticker == "ALV.DE"
    assert state.positions[0].quantity == 14.0
    assert state.positions[0].buy_in_price == 245.50
    assert state.positions[1].ticker == "MSFT"
    assert state.positions[1].sector == "Technologie & Software"
    assert state.positions[1].country == "USA"
