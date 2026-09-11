from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from spendee_sync.models.transaction import Transaction, TransactionType
from spendee_sync.utils.categorizer import load_labels_from_file, assign_labels

MONOBANK_API = "https://api.monobank.ua"

CURRENCY_NUM_TO_ALPHA = {
    980: "UAH",
    840: "USD",
    978: "EUR",
    756: "CHF",
}


class MonobankService:
    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.getenv("MONOBANK_TOKEN")
        if not self.token:
            raise ValueError("MONOBANK_TOKEN is required. Set it in environment or .env file.")
        self.session = requests.Session()
        self.session.headers.update({"X-Token": self.token})

    @retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
    def _get(self, path: str, **params):
        resp = self.session.get(f"{MONOBANK_API}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_client_info(self) -> dict:
        return self._get("/personal/client-info")

    def get_account(self) -> dict:
        info = self.get_client_info()
        iban = os.getenv("IBAN")
        card_type = os.getenv("CARD_TYPE")
        accounts = info.get("accounts", [])
        accounts = [
            a for a in accounts if "iban" in a and a["iban"] == iban and a["type"] == card_type
        ]
        if not any(accounts):
            raise ValueError(f"Account with IBAN {iban} not found")
        return accounts[0]

    def fetch_statements(self, account_id: str, since: datetime, until: datetime) -> list[dict]:
        since_unix = int(since.replace(tzinfo=timezone.utc).timestamp())
        until_unix = int(until.replace(tzinfo=timezone.utc).timestamp())
        return self._get(f"/personal/statement/{account_id}/{since_unix}/{until_unix}")

    def fetch_transactions(self, days: int = 30) -> list[Transaction]:
        until = datetime.now(timezone.utc)
        transactions: list[Transaction] = []
        account = self.get_account()
        account_id = account["id"]

        # Split into 30-day chunks if needed
        chunks = []
        current_until = until
        total_days = days

        while total_days > 0:
            chunk_days = min(30, total_days)
            current_since = current_until - timedelta(days=chunk_days)
            chunks.append((current_since, current_until))
            current_until = current_since
            total_days -= chunk_days

        # Fetch statements for each chunk
        all_raw_items = []
        for i, (chunk_since, chunk_until) in enumerate(chunks):
            raw_items = self.fetch_statements(account_id, chunk_since, chunk_until)
            all_raw_items.extend(raw_items)
            # Monobank API rate limit: 1 request per 60 seconds for statements
            # Add delay between requests to avoid rate limiting (except for the last chunk)
            if i < len(chunks) - 1:
                time.sleep(60)

        # save to json file
        # with open("raw_items.json", "w") as f:
        #     json.dump(all_raw_items, f)

        # load label rules once
        label_rules = load_labels_from_file()
        for item in all_raw_items:
            amount = Decimal(item.get("amount", 0) / 100)
            amount = amount.quantize(Decimal("0.01"))
            operation_amount = Decimal(item.get("operationAmount", 0) / 100)
            operation_amount = operation_amount.quantize(Decimal("0.01"))
            currency_code = item.get("currencyCode", 980)
            description = item.get("description", "")
            time_unix = item.get("time")
            dt = datetime.fromtimestamp(time_unix, tz=timezone.utc)
            tx_type = TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE
            # derive labels from description
            labels_list = assign_labels(description, label_rules)
            comment = item.get("comment", "") or ""
            transactions.append(
                Transaction(
                    id=str(item.get("id")) if item.get("id") is not None else None,
                    date=dt,
                    primary_amount=operation_amount,
                    second_amount=amount,
                    currency=CURRENCY_NUM_TO_ALPHA.get(int(currency_code), str(currency_code)),
                    mcc=item.get("mcc"),
                    description=description,
                    comment=comment,
                    labels=labels_list or None,
                    type=tx_type,
                    account_id=account_id,
                    wallet=None,
                    category=None,
                    source="monobank",
                    raw=item,
                )
            )
        return transactions


def main() -> None:
    mono = MonobankService()
    txs = mono.fetch_transactions(days=30)
    print(txs)


if __name__ == "__main__":
    main()
