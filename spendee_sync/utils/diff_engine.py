from __future__ import annotations

from datetime import timedelta
from typing import Iterable, Set

from ..models import Transaction


def build_index(transactions: Iterable[Transaction]) -> Set[tuple]:
    return {t.unique_key() for t in transactions}


def compute_missing(monobank_txs: Iterable[Transaction], spendee_txs: Iterable[Transaction]) -> list[Transaction]:
    spendee_index = build_index(spendee_txs)
    missing = [t for t in monobank_txs if t.unique_key() not in spendee_index]
    return missing


def compute_missing_fuzzy(
    monobank_txs: Iterable[Transaction],
    spendee_txs: Iterable[Transaction],
    date_tolerance_hours: int = 25,
) -> list[Transaction]:
    """Return Monobank transactions not found in Spendee, using fuzzy date matching.

    For each Monobank transaction not matched by exact key, checks whether a
    Spendee transaction exists with the same amount/type but a date shifted by
    up to +/-date_tolerance_hours hours. This handles UTC vs local timezone edge
    cases where the same transaction lands on different calendar dates.
    """
    spendee_list = list(spendee_txs)
    spendee_index = build_index(spendee_list)

    # Build a set of (date, abs_amount, type) tuples for fuzzy look-up
    spendee_amount_type: Set[tuple] = {
        (t.date.date(), abs(t.second_amount), t.type.value) for t in spendee_list
    }

    missing = []
    delta = timedelta(hours=date_tolerance_hours)

    for tx in monobank_txs:
        if tx.unique_key() in spendee_index:
            # Exact match -- already present in Spendee
            continue

        # Try shifted dates within the tolerance window
        matched = False
        shifted = tx.date - delta
        while shifted <= tx.date + delta:
            candidate_key = (shifted.date(), abs(tx.second_amount), tx.type.value)
            if candidate_key in spendee_amount_type:
                matched = True
                break
            shifted += timedelta(hours=1)

        if not matched:
            missing.append(tx)

    return missing
