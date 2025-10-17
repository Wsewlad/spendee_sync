from __future__ import annotations

from typing import Iterable, Set

from ..models import Transaction


def build_index(transactions: Iterable[Transaction]) -> Set[tuple]:
    return {t.unique_key() for t in transactions}


def compute_missing(monobank_txs: Iterable[Transaction], spendee_txs: Iterable[Transaction]) -> list[Transaction]:
    spendee_index = build_index(spendee_txs)
    missing = [t for t in monobank_txs if t.unique_key() not in spendee_index]
    return missing


