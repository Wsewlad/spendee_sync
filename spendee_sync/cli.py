"""Click-based CLI for spendee-sync."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv


@click.group()
def cli() -> None:
    """Spendee Sync — synchronise Monobank transactions to Spendee."""
    load_dotenv()


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

@cli.command("fetch")
@click.option("--days", default=30, show_default=True, help="Number of days of history to fetch.")
@click.option(
    "--output",
    default="spendee_sync/outputs/monobank_transactions.json",
    show_default=True,
    help="Path for the output JSON file.",
)
def fetch(days: int, output: str) -> None:
    """Fetch transactions from Monobank and save them to a JSON file."""
    from spendee_sync.services.monobank import MonobankService

    click.echo(f"Fetching {days} days of Monobank transactions…")
    service = MonobankService()
    transactions = service.fetch_transactions(days=days)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump([tx.to_dict() for tx in transactions], f, ensure_ascii=False, indent=2)

    click.echo(f"Saved {len(transactions)} transactions to {out_path}")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

@cli.command("sync")
@click.option("--days", default=90, show_default=True, help="Number of days of history to fetch.")
@click.option(
    "--input",
    "spendee_input",
    default="spendee_sync/inputs/transactions_export.csv",
    show_default=True,
    help="Path to the Spendee export CSV file.",
)
@click.option(
    "--output-dir",
    default="spendee_sync/outputs",
    show_default=True,
    help="Directory where output files will be written.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would be exported without writing any files.",
)
def sync(days: int, spendee_input: str, output_dir: str, dry_run: bool) -> None:
    """Full sync workflow: fetch → categorize → diff → export CSV."""
    from spendee_sync.services.monobank import MonobankService
    from spendee_sync.services.spendee import SpendeeService
    from spendee_sync.utils.categorizer import categorize_transaction, load_rules_from_env
    from spendee_sync.utils.diff_engine import compute_missing
    from spendee_sync.task import export_comparison_csv, export_comparison_json

    click.echo(f"Fetching {days} days of Monobank transactions…")
    mono_service = MonobankService()
    spendee_service = SpendeeService()
    mcc_rules, keyword_patterns = load_rules_from_env()

    mono_txs = [
        categorize_transaction(t, mcc_rules, keyword_patterns)
        for t in mono_service.fetch_transactions(days=days)
    ]
    click.echo(f"Fetched {len(mono_txs)} transactions from Monobank.")

    click.echo(f"Parsing Spendee export from {spendee_input}…")
    spendee_txs = spendee_service.parse_export(spendee_input)
    click.echo(f"Found {len(spendee_txs)} transactions in Spendee export.")

    missing = [
        categorize_transaction(t, mcc_rules, keyword_patterns)
        for t in compute_missing(mono_txs, spendee_txs)
    ]
    click.echo(f"Found {len(missing)} transactions missing from Spendee.")

    missing_keys = {tx.unique_key() for tx in missing}
    existing_mono = [tx for tx in mono_txs if tx.unique_key() not in missing_keys]

    if dry_run:
        click.echo("[dry-run] Would export the following missing transactions:")
        for tx in missing:
            click.echo(f"  {tx.date.date()} | {tx.description} | {tx.second_amount} {tx.currency}")
        click.echo(f"[dry-run] Total: {len(missing)} transactions would be written to {output_dir}/")
        return

    out = Path(output_dir)
    missing_csv = str(out / "missing_for_spendee.csv")
    existing_csv = str(out / "existing_in_spendee.csv")
    existing_json = str(out / "existing_in_spendee.json")

    spendee_service.export_csv(missing, missing_csv)
    click.echo(f"Exported {len(missing)} missing transactions → {missing_csv}")

    export_comparison_csv(existing_mono, spendee_txs, existing_csv)
    click.echo(f"Exported comparison CSV → {existing_csv}")

    export_comparison_json(existing_mono, spendee_txs, existing_json)
    click.echo(f"Exported comparison JSON → {existing_json}")


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

@cli.command("compare")
@click.option(
    "--mono-json",
    required=True,
    help="Path to the Monobank transactions JSON file (from `fetch`).",
)
@click.option(
    "--spendee-csv",
    required=True,
    help="Path to the Spendee export CSV file.",
)
@click.option(
    "--output",
    default="spendee_sync/outputs/comparison_report.json",
    show_default=True,
    help="Path for the output comparison report (JSON).",
)
def compare(mono_json: str, spendee_csv: str, output: str) -> None:
    """Generate a comparison report between Monobank and Spendee transactions."""
    from decimal import Decimal
    from datetime import datetime, timezone
    from spendee_sync.services.spendee import SpendeeService
    from spendee_sync.models.transaction import Transaction, TransactionType
    from spendee_sync.utils.categorizer import categorize_transaction, load_rules_from_env
    from spendee_sync.task import export_comparison_json

    click.echo(f"Loading Monobank transactions from {mono_json}…")
    with open(mono_json, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    mcc_rules, keyword_patterns = load_rules_from_env()

    mono_txs = []
    for item in raw_list:
        tx = Transaction(
            id=item.get("id") or "",
            date=datetime.fromisoformat(item["date"]),
            primary_amount=Decimal(str(item.get("primary_amount", 0))),
            second_amount=Decimal(str(item.get("second_amount", 0))),
            currency=item.get("currency", "UAH"),
            mcc=item.get("mcc") or 0,
            description=item.get("description", ""),
            comment=item.get("comment", "") or "",
            labels=item.get("labels"),
            type=TransactionType(item["type"]) if item.get("type") else TransactionType.EXPENSE,
            account_id=item.get("account_id", ""),
            category=item.get("category"),
            source=item.get("source", "monobank"),
        )
        mono_txs.append(categorize_transaction(tx, mcc_rules, keyword_patterns))

    click.echo(f"Loaded {len(mono_txs)} Monobank transactions.")

    click.echo(f"Parsing Spendee export from {spendee_csv}…")
    spendee_service = SpendeeService()
    spendee_txs = spendee_service.parse_export(spendee_csv)
    click.echo(f"Found {len(spendee_txs)} Spendee transactions.")

    export_comparison_json(mono_txs, spendee_txs, output)
    click.echo(f"Comparison report written to {output}")


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@cli.command("import")
@click.option("--file", "filepath", required=True, help="Path to the CSV file to import into Spendee.")
@click.option("--wallet", default=None, help="Wallet name to import transactions into.")
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Run the browser in headless mode.",
)
def import_cmd(filepath: str, wallet: str | None, headless: bool) -> None:
    """Trigger a Selenium-based import of a CSV file into the Spendee web app."""
    from spendee_sync.services.spendee import SpendeeService

    click.echo(f"Importing {filepath} into Spendee{' (headless)' if headless else ''}…")
    service = SpendeeService()
    service.import_file(filepath=filepath, wallet_name=wallet, headless=headless)
    click.echo("Import complete.")


if __name__ == "__main__":
    cli()
