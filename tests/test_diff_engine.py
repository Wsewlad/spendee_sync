from datetime import datetime, timezone
from decimal import Decimal

from spendee_sync.models import Transaction
from spendee_sync.models.transaction import TransactionType
from spendee_sync.utils.diff_engine import compute_missing


def _make_transaction(id: str, amount: str, description: str) -> Transaction:
    return Transaction(
        id=id,
        date=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        primary_amount=Decimal(amount),
        second_amount=Decimal(amount),
        currency="UAH",
        mcc=5411,
        description=description,
        comment="",
        labels=[],
        type=TransactionType.EXPENSE,
        account_id="acc-1",
    )


def test_compute_missing_returns_transactions_not_in_spendee():
    monobank_txs = [
        _make_transaction("m1", "-100.00", "Grocery store"),
        _make_transaction("m2", "-50.00", "Coffee shop"),
    ]
    spendee_txs = [_make_transaction("s1", "-100.00", "Grocery store")]

    missing = compute_missing(monobank_txs, spendee_txs)

    assert [t.id for t in missing] == ["m2"]


def test_compute_missing_returns_empty_when_all_present():
    txs = [_make_transaction("m1", "-100.00", "Grocery store")]

    assert compute_missing(txs, txs) == []
