from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from spendee_sync.config import SpendeeSyncConfig
from spendee_sync.services.monobank import MonobankService
from spendee_sync.services.wise import WiseService
from spendee_sync.utils.categorizer import categorize_transaction, load_rules_from_env
from spendee_sync.services.spendee import SpendeeService
from spendee_sync.utils.diff_engine import compute_missing, compute_missing_fuzzy
from spendee_sync.utils.notifier import Notifier
from spendee_sync.utils.state import ImportStateDB


def export_comparison_csv(mono_txs: list, spendee_txs: list, output_path: str) -> None:
    """Export a comparison CSV showing both Monobank and Spendee versions of existing transactions."""
    spendee_map = {tx.unique_key(): tx for tx in spendee_txs}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Date", "Description",
            "Mono Amount", "Spendee Amount", "Diff",
            "Mono Category", "Spendee Category", "Match",
            "Mono Labels", "Spendee Labels"
        ])

        for mono_tx in mono_txs:
            spendee_tx = spendee_map.get(mono_tx.unique_key())
            if not spendee_tx:
                continue

            writer.writerow([
                mono_tx.date.date().isoformat(),
                mono_tx.description,
                f"{mono_tx.second_amount:.2f}",
                f"{spendee_tx.second_amount:.2f}",
                f"{abs(mono_tx.second_amount - spendee_tx.second_amount):.2f}",
                mono_tx.category or "",
                spendee_tx.category or "",
                "✓" if mono_tx.category == spendee_tx.category else "✗",
                ", ".join(mono_tx.labels or []),
                ", ".join(spendee_tx.labels or [])
            ])


def export_comparison_json(mono_txs: list, spendee_txs: list, output_path: str) -> None:
    """Export a comparison JSON showing both Monobank and Spendee versions of existing transactions."""
    spendee_map = {tx.unique_key(): tx for tx in spendee_txs}

    comparisons = []
    for mono_tx in mono_txs:
        spendee_tx = spendee_map.get(mono_tx.unique_key())
        if not spendee_tx:
            continue

        comparisons.append({
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
                "amount_diff": float(abs(mono_tx.second_amount - spendee_tx.second_amount))
            }
        })

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

    state_db = ImportStateDB()
    mono_service = MonobankService()
    spendee_service = SpendeeService()
    mcc_rules, keyword_patterns = load_rules_from_env()
    mono_txs = [categorize_transaction(t, mcc_rules, keyword_patterns) for t in mono_service.fetch_transactions(days=days)]
    spendee_txs = spendee_service.parse_export(spendee_xlsx)
    missing = [categorize_transaction(t, mcc_rules, keyword_patterns) for t in compute_missing_fuzzy(mono_txs, spendee_txs)]

    # Filter out transactions already recorded in the state DB
    missing = state_db.filter_already_imported(missing)

    # Export missing transactions
    spendee_service.export_csv(missing, missing_csv_path)

    # Record the exported transactions in the state DB
    state_db.mark_imported(missing)

    # Find existing transactions (transactions in both mono and spendee)
    missing_keys = {tx.unique_key() for tx in missing}
    existing_mono = [tx for tx in mono_txs if tx.unique_key() not in missing_keys]

    # Export existing transactions comparison (CSV and JSON)
    export_comparison_csv(existing_mono, spendee_txs, existing_csv_path)
    export_comparison_json(existing_mono, spendee_txs, existing_json_path)

    # Send notifications
    categories = dict(Counter(tx.category or "Uncategorized" for tx in missing))
    Notifier().notify_sync_complete(
        fetched=len(mono_txs),
        missing=len(missing),
        categories=categories,
        output_path=missing_csv_path,
    )


def _safe_filename(name: str) -> str:
    """Convert an account name into a safe filesystem-friendly string."""
    return re.sub(r"[^\w\-]+", "_", name).strip("_").lower()


def task_multi_account(config_path: Optional[str] = None, days: int = 90) -> None:
    """Sync all accounts defined in the YAML config file (or env vars if no config)."""
    load_dotenv()
    config = SpendeeSyncConfig.load(config_path)
    mcc_rules, keyword_patterns = load_rules_from_env()
    spendee_service = SpendeeService()

    for account in config.accounts:
        slug = _safe_filename(account.name)
        missing_csv_path = f"spendee_sync/outputs/{slug}_missing_for_spendee.csv"
        existing_csv_path = f"spendee_sync/outputs/{slug}_existing_in_spendee.csv"
        existing_json_path = f"spendee_sync/outputs/{slug}_existing_in_spendee.json"
        spendee_xlsx = "spendee_sync/inputs/transactions_export.csv"

        account_type = account.type.lower()
        if account_type == "monobank":
            service = MonobankService(
                token=account.token,
                iban=account.iban,
                card_type=account.card_type,
            )
        elif account_type == "wise":
            service = WiseService(
                token=account.token,
                profile_id=account.profile_id,
            )
        else:
            raise ValueError(
                f"Unsupported account type '{account.type}' for account '{account.name}'."
            )

        raw_txs = service.fetch_transactions(days=days)
        txs = [categorize_transaction(t, mcc_rules, keyword_patterns) for t in raw_txs]
        spendee_txs = spendee_service.parse_export(spendee_xlsx)
        missing = [
            categorize_transaction(t, mcc_rules, keyword_patterns)
            for t in compute_missing(txs, spendee_txs)
        ]

        spendee_service.export_csv(missing, missing_csv_path)

        missing_keys = {tx.unique_key() for tx in missing}
        existing = [tx for tx in txs if tx.unique_key() not in missing_keys]
        export_comparison_csv(existing, spendee_txs, existing_csv_path)
        export_comparison_json(existing, spendee_txs, existing_json_path)


def main():
    """Entry point for CLI command."""
    task()


if __name__ == "__main__":
    main()
    