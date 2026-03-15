"""Standalone analytics script.

Usage:
    python -m spendee_sync.analyze                            # uses default Spendee export path
    python -m spendee_sync.analyze --input path/to/export.csv
    python -m spendee_sync.analyze --source monobank --days 90
    python -m spendee_sync.analyze --input export.csv --output report.html
"""
from __future__ import annotations

import argparse
import sys
import webbrowser

from dotenv import load_dotenv

from spendee_sync.analytics.report import build_report
from spendee_sync.services.spendee import SpendeeService
from spendee_sync.utils.categorizer import categorize_transaction, load_rules_from_env


def _load_from_spendee(path: str) -> list:
    service = SpendeeService()
    txs = service.parse_export(path)
    if not txs:
        print(f"[error] No transactions found in {path!r}", file=sys.stderr)
        sys.exit(1)
    mcc_rules, keyword_patterns = load_rules_from_env()
    return [categorize_transaction(tx, mcc_rules, keyword_patterns) for tx in txs]


def _load_from_monobank(days: int) -> list:
    from spendee_sync.services.monobank import MonobankService
    service = MonobankService()
    txs = service.fetch_transactions(days=days)
    mcc_rules, keyword_patterns = load_rules_from_env()
    return [categorize_transaction(tx, mcc_rules, keyword_patterns) for tx in txs]


def _load_from_wise(days: int) -> list:
    from spendee_sync.services.wise import WiseService
    service = WiseService()
    return service.fetch_transactions(days=days)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate spending analytics report.")
    parser.add_argument(
        "--source",
        choices=["spendee", "monobank", "wise"],
        default="spendee",
        help="Data source (default: spendee)",
    )
    parser.add_argument(
        "--input",
        default="spendee_sync/inputs/transactions_export.csv",
        help="Path to Spendee export CSV (used when --source=spendee)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days to fetch (used when --source=monobank or wise)",
    )
    parser.add_argument(
        "--output",
        default="spendee_sync/outputs/report.html",
        help="Output HTML report path",
    )
    parser.add_argument(
        "--title",
        default="Spending Analytics",
        help="Report title",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        default=False,
        help="Open the report in the browser after generating",
    )
    args = parser.parse_args()

    if args.source == "spendee":
        print(f"Loading transactions from Spendee export: {args.input}")
        transactions = _load_from_spendee(args.input)
    elif args.source == "monobank":
        print(f"Fetching {args.days} days of Monobank transactions...")
        transactions = _load_from_monobank(args.days)
    else:
        print(f"Fetching {args.days} days of Wise transactions...")
        transactions = _load_from_wise(args.days)

    print(f"Loaded {len(transactions)} transactions.")
    report_path = build_report(transactions, output_path=args.output, title=args.title)
    print(f"Report written to: {report_path}")

    if args.open:
        webbrowser.open(f"file://{report_path}")


if __name__ == "__main__":
    main()
