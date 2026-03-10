from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from enum import Enum
from pydantic import BaseModel
from typing import Optional, List


class TransactionType(Enum):
    INCOME = "Income"
    EXPENSE = "Expense"


class Transaction(BaseModel):
    id: str
    date: datetime
    primary_amount: Decimal
    second_amount: Decimal
    currency: str
    mcc: int
    description: str
    comment: str
    labels: Optional[List[str]]
    type: TransactionType
    account_id: str
    wallet: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    raw: Optional[dict[str, Any]] = None

    def unique_key(self) -> tuple:
        """Generate unique key for transaction deduplication.

        Uses date, amount, type to identify duplicates.
        """
        return (self.date.date(), abs(self.second_amount), self.type.value)

    def to_dict(self) -> dict:
        """Export transaction as a dictionary for JSON serialization."""
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "description": self.description,
            "second_amount": float(self.second_amount),
            "primary_amount": float(self.primary_amount),
            "currency": self.currency,
            "category": self.category,
            "labels": self.labels,
            "mcc": self.mcc,
            "type": self.type.value if self.type else None,
            "comment": self.comment,
            "source": self.source,
        }

    def to_csv_row(self) -> list:
        """Export transaction as a CSV row."""
        return [
            self.date.date().isoformat(),
            self.type.value if self.type else "",
            self.category or "",
            f"{self.second_amount:.2f}",
            self.description or "",
            ", ".join(self.labels or []),
        ]
