from __future__ import annotations

import csv
import json
from pathlib import Path

from dotenv import load_dotenv

from spendee_sync.services.monobank import MonobankService
from spendee_sync.utils.categorizer import categorize_transaction, load_rules_from_env
from spendee_sync.services.spendee import SpendeeService
from spendee_sync.utils.diff_engine import compute_missing


def export_comparison_csv(mono_txs: list, spendee_txs: list, output_path: str) -> None:
    """Export a comparison CSV showing both Monobank and Spendee versions of a transaction."""
    spendee_map = {tx.unique_key(): tx for tx in spendee_txs}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Date",
                "Description",
                "Mono Amount",
                "Spendee Amount",
                "Diff",
                "Mono Category",
                "Spendee Category",
                "Match",
                "Mono Labels",
                "Spendee Labels",
            ]
        )

        for mono_tx in mono_txs:
            spendee_tx = spendee_map.get(mono_tx.unique_key())
            if not spendee_tx:
                continue

            writer.writerow(
                [
                    mono_tx.date.date().isoformat(),
                    mono_tx.description,
                    f"{mono_tx.second_amount:.2f}",
                    f"{spendee_tx.second_amount:.2f}",
                    f"{abs(mono_tx.second_amount - spendee_tx.second_amount):.2f}",
                    mono_tx.category or "",
                    spendee_tx.category or "",
                    "✓" if mono_tx.category == spendee_tx.category else "✗",
                    ", ".join(mono_tx.labels or []),
                    ", ".join(spendee_tx.labels or []),
                ]
            )


def export_comparison_json(mono_txs: list, spendee_txs: list, output_path: str) -> None:
    """Export a comparison JSON showing both Monobank and Spendee versions of a transaction."""
    spendee_map = {tx.unique_key(): tx for tx in spendee_txs}

    comparisons = []
    for mono_tx in mono_txs:
        spendee_tx = spendee_map.get(mono_tx.unique_key())
        if not spendee_tx:
            continue

        comparisons.append(
            {
                "date": mono_tx.date.isoformat(),
                "description": mono_tx.description,
                "monobank": {
                    "second_amount": float(mono_tx.second_amount),
                    "category": mono_tx.category,
                    "labels": mono_tx.labels,
                    "currency": mono_tx.currency,
                    "primary_amount": float(mono_tx.primary_amount),
                },
                "spendee": {
                    "second_amount": float(spendee_tx.second_amount),
                    "category": spendee_tx.category,
                    "labels": spendee_tx.labels,
                },
                "matches": {
                    "category": mono_tx.category == spendee_tx.category,
                    "labels": mono_tx.labels == spendee_tx.labels,
                    "amount_diff": float(abs(mono_tx.second_amount - spendee_tx.second_amount)),
                },
            }
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparisons, f, ensure_ascii=False, indent=2)


def task():
    load_dotenv()
    days = 90
    spendee_xlsx = "spendee_sync/inputs/transactions_export.csv"
    missing_csv_path = "spendee_sync/outputs/missing_for_spendee.csv"
    existing_csv_path = "spendee_sync/outputs/existing_in_spendee.csv"
    existing_json_path = "spendee_sync/outputs/existing_in_spendee.json"

    mono_service = MonobankService()
    spendee_service = SpendeeService()
    mcc_rules, keyword_patterns = load_rules_from_env()
    mono_txs = [
        categorize_transaction(t, mcc_rules, keyword_patterns)
        for t in mono_service.fetch_transactions(days=days)
    ]
    spendee_txs = spendee_service.parse_export(spendee_xlsx)
    missing = [
        categorize_transaction(t, mcc_rules, keyword_patterns)
        for t in compute_missing(mono_txs, spendee_txs)
    ]

    # Export missing transactions
    spendee_service.export_csv(missing, missing_csv_path)

    # Find existing transactions (transactions in both mono and spendee)
    missing_keys = {tx.unique_key() for tx in missing}
    existing_mono = [tx for tx in mono_txs if tx.unique_key() not in missing_keys]

    # Export existing transactions comparison (CSV and JSON)
    export_comparison_csv(existing_mono, spendee_txs, existing_csv_path)
    export_comparison_json(existing_mono, spendee_txs, existing_json_path)


def main():
    """Entry point for CLI command."""
    task()


if __name__ == "__main__":
    main()
