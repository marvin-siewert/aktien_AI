"""
Standalone CLI Script for the Daily Sentinel ('Täglicher Kurssprung-Wächter').

Can be run via Terminal or Windows Task Scheduler / Cron:
    python daily_sentinel.py --threshold 5.0 --lang de

Checks ONLY current portfolio positions in `data/portfolio_active.json` for daily price
jumps exceeding +/- threshold %, fetches 24-hour news for triggered holdings, and checks
whether stored buy theses in `data/portfolio_thesis.json` are CONFIRMED, BROKEN, or UNTOUCHED.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from src.core.portfolio_manager import PortfolioManager
from src.core.sentinel_engine import SentinelEngine
from src.models.entities import SentinelAlert
from src.storage.json_store import JsonStore


def trigger_optional_alert_hook(triggered_alerts: List[SentinelAlert]) -> None:
    """
    Extension hook for desktop notifications, email alerts, or Telegram/Webhook messages
    whenever at least one holding triggers a CONFIRMED or BROKEN thesis alert.
    """
    critical = [a for a in triggered_alerts if a.status in ("BROKEN", "CONFIRMED")]
    if not critical:
        return
    print("\n" + "=" * 72)
    print(f"[ALERT HOOK] {len(critical)} critical thesis event(s) detected:")
    for alert in critical:
        print(f"  -> [{alert.status}] {alert.company_name} ({alert.ticker}): {alert.daily_change_pct:+.2f}%")
        print(f"     Action: {alert.action_recommendation}")
    print("=" * 72)


def main(argv: List[str] | None = None) -> int:
    """CLI entry point for the Daily Sentinel."""
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Daily Sentinel: Monitors portfolio holdings for unusual daily moves and checks saved buy theses."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="Daily percentage move trigger threshold (default: 5.0 for +/- 5%%)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="de",
        choices=["de", "en"],
        help="Output language for AI reasoning ('de' or 'en')",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Use cached market prices instead of forcing a live refresh",
    )
    args = parser.parse_args(argv)

    store = JsonStore()
    pm = PortfolioManager(store=store)
    engine = SentinelEngine(store=store)

    portfolio = pm.state
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Running Daily Sentinel for '{portfolio.portfolio_name}'")
    print(f"Holdings: {len(portfolio.positions)} | Trigger Threshold: +/- {args.threshold:.1f}%\n")

    alerts = engine.run_sentinel_check(
        portfolio=portfolio,
        threshold_pct=args.threshold,
        use_cache=args.use_cache,
        language=args.lang,
    )

    # Persist last sentinel run report in data/sentinel_last_run.json
    store.write_json(
        "sentinel_last_run.json",
        {
            "ran_at": datetime.now().isoformat(timespec="seconds"),
            "threshold_pct": args.threshold,
            "alerts": [a.model_dump() for a in alerts],
        },
    )

    triggered = [a for a in alerts if a.triggered]
    for alert in alerts:
        flag = "🚨 TRIGGERED" if alert.triggered else "OK"
        print(
            f"[{flag}] {alert.ticker:<8} | {alert.daily_change_pct:+6.2f}% | "
            f"Status: {alert.status:<10} | {alert.reasoning}"
        )
        for url in alert.cited_urls:
            print(f"         Source: {url}")

    trigger_optional_alert_hook(triggered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
