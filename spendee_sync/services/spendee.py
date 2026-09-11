from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from spendee_sync.models.transaction import Transaction, TransactionType

SPENDEE_URL = "https://web.spendee.com"
SPENDEE_COLUMNS = [
    "Date",
    "Type",
    "Category name",
    "Amount",
    "Note",
    "Labels",
]


def _row_for_spendee(tx: Transaction) -> list[str]:
    """Convert Transaction to Spendee CSV row format.

    Args:
        tx: Transaction to convert

    Returns:
        List of strings matching SPENDEE_COLUMNS format
    """
    from datetime import timezone as _tz

    date_str = tx.date.astimezone(_tz.utc).isoformat(timespec="seconds")
    tx_type = (
        TransactionType.INCOME.value if tx.second_amount >= 0 else TransactionType.EXPENSE.value
    )
    category_name = tx.category or ""
    amount_str = f"{tx.second_amount:.2f}"
    labels = ", ".join(tx.labels) if getattr(tx, "labels", None) else ""

    # Build note with description, original amount, currency, and exchange rate
    note_parts = []
    if tx.description:
        note_parts.append(tx.description)

    # Add original amount, currency, and exchange rate if different from UAH
    if tx.currency and tx.currency != "UAH" and tx.primary_amount != 0:
        original_amount_str = f"{abs(tx.primary_amount):.2f}"
        # Calculate exchange rate
        exchange_rate = abs(tx.second_amount) / abs(tx.primary_amount)
        note_parts.append(f"({original_amount_str} {tx.currency} @ {exchange_rate:.2f})")

    note = " ".join(note_parts)

    return [date_str, tx_type, category_name, amount_str, note, labels]


class SpendeeService:
    def parse_export(self, path: str) -> list[Transaction]:
        """Parse a Spendee export file.

        Supports CSV exports with headers: Date, Wallet, Type, Category name,
        Amount, Currency, Note, Labels, Author.
        Also keeps backward-compat for XLSX by falling back to previous logic
        when extension is .xlsx/.xls.
        """
        from decimal import Decimal
        from datetime import timezone as _tz

        ext = str(Path(path)).lower()

        # CSV path
        if ext.endswith(".csv"):
            transactions: list[Transaction] = []
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse columns per observed schema
                    date_str = (row.get("Date") or "").strip()
                    dt = pd.to_datetime(
                        date_str,
                        utc=True,
                        errors="coerce",
                    ).to_pydatetime()
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=_tz.utc)

                    amount_str = (row.get("Amount") or "0").strip()
                    try:
                        amount = Decimal(str(amount_str))
                    except Exception:
                        amount = Decimal("0")
                    amount = amount.quantize(Decimal("0.01"))

                    currency = (row.get("Currency") or "").strip()
                    category = (row.get("Category name") or "").strip() or None
                    note = (row.get("Note") or "").strip()
                    labels_str = (row.get("Labels") or "").strip()
                    labels = (
                        [s.strip() for s in labels_str.split(",") if s.strip()]
                        if labels_str
                        else []
                    )
                    wallet = (row.get("Wallet") or "").strip()
                    tx_type_raw = (row.get("Type") or "").strip()
                    tx_type = TransactionType(tx_type_raw)

                    transactions.append(
                        Transaction(
                            id="",
                            date=dt,
                            primary_amount=amount,
                            second_amount=amount,
                            currency=currency,
                            mcc=0,
                            description=note,
                            comment="",
                            labels=labels or None,
                            type=tx_type,
                            account_id=wallet,
                            wallet=wallet or None,
                            category=category,
                            source="spendee",
                            raw=row,
                        )
                    )
            return transactions
        return []

    def export_csv(self, transactions: Iterable[Transaction], output_path: str) -> str:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(SPENDEE_COLUMNS)
            for tx in transactions:
                writer.writerow(_row_for_spendee(tx))
        return str(out)

    def export_xlsx(self, transactions: Iterable[Transaction], output_path: str) -> str:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([_row_for_spendee(tx) for tx in transactions], columns=SPENDEE_COLUMNS)
        df.to_excel(out, index=False)
        return str(out)

    def import_file(
        self,
        filepath: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        wallet_name: Optional[str] = None,
        headless: bool = False,
    ) -> None:
        def _get_env(name: str, default: Optional[str] = None) -> str:
            val = os.getenv(name, default)
            if val is None or val == "":
                raise ValueError(f"Missing required env: {name}")
            return val

        email = email or _get_env("SPENDEE_EMAIL")
        password = password or _get_env("SPENDEE_PASSWORD")
        fp = str(Path(filepath).expanduser().resolve())

        chrome_options = webdriver.ChromeOptions()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1280,900")

        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=chrome_options,
        )
        wait = WebDriverWait(driver, 30)
        try:
            driver.get(SPENDEE_URL)

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
            driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys(email)
            driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(password)
            driver.find_element(By.XPATH, "//button[contains(., 'Log in')] ").click()

            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Import')]")))
            driver.find_element(By.XPATH, "//*[contains(text(),'Import')]").click()

            if wallet_name:
                try:
                    wait.until(
                        EC.element_to_be_clickable((By.XPATH, "//div[@role='combobox']"))
                    ).click()
                    wait.until(
                        EC.element_to_be_clickable(
                            (By.XPATH, f"//div[@role='option' and contains(., '{wallet_name}')]"),
                        )
                    ).click()
                except Exception:
                    pass

            file_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(fp)

            try:
                wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Import')]"))
                ).click()
            except Exception:
                pass

            wait.until(lambda d: True)
        finally:
            driver.quit()


if __name__ == "__main__":
    service = SpendeeService()
    txs = service.parse_export("spendee_sync/transactions_export.csv")
    print(txs)
