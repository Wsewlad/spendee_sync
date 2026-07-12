from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from spendee_sync.models.transaction import Transaction, TransactionType
from spendee_sync.services.spendee import SpendeeService

# This test drives a real browser login and uploads a transaction into your
# actual Spendee wallet, so it needs an explicit second opt-in on top of
# credentials to avoid accidentally polluting real account data on a plain
# `pytest` run.
REQUIRED_ENV = ["SPENDEE_EMAIL", "SPENDEE_PASSWORD"]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (all(os.getenv(var) for var in REQUIRED_ENV) and os.getenv("RUN_SPENDEE_IMPORT_TEST") == "1"),
        reason=(
            f"requires {', '.join(REQUIRED_ENV)} plus RUN_SPENDEE_IMPORT_TEST=1 "
            "(this test imports a real transaction into your Spendee wallet)"
        ),
    ),
]


def test_import_file_uploads_via_browser(tmp_path, chrome_available):
    if not chrome_available:
        pytest.skip("no Chrome/Chromium binary found on PATH")

    tx = Transaction(
        id="",
        date=datetime.now(timezone.utc),
        primary_amount=Decimal("0.01"),
        second_amount=Decimal("0.01"),
        currency="UAH",
        mcc=0,
        description="spendee_sync integration test",
        comment="",
        labels=None,
        type=TransactionType.EXPENSE,
        account_id="",
        source="test",
    )
    service = SpendeeService()
    csv_path = service.export_csv([tx], str(tmp_path / "integration_test.csv"))

    service.import_file(
        filepath=csv_path,
        wallet_name=os.getenv("WALLET_NAME"),
        headless=True,
    )
