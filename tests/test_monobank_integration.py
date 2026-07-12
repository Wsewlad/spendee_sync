from __future__ import annotations

import os

import pytest

from spendee_sync.services.monobank import MonobankService

REQUIRED_ENV = ["MONOBANK_TOKEN", "IBAN", "CARD_TYPE"]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not all(os.getenv(var) for var in REQUIRED_ENV),
        reason=f"requires {', '.join(REQUIRED_ENV)} in the environment/.env",
    ),
]


def test_get_account_matches_configured_iban():
    service = MonobankService()
    account = service.get_account()
    assert account["iban"] == os.getenv("IBAN")
    assert account["type"] == os.getenv("CARD_TYPE")


def test_fetch_transactions_recent_window():
    service = MonobankService()
    # Single day keeps this under Monobank's 1 request/60s statement rate limit.
    transactions = service.fetch_transactions(days=1)
    assert isinstance(transactions, list)
