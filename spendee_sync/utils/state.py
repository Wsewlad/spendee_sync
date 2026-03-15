import sqlite3
from pathlib import Path
from datetime import datetime


class ImportStateDB:
    def __init__(self, db_path: str = "spendee_sync_state.db"):
        """Create/open SQLite DB. Schema: imported_transactions(tx_key TEXT PRIMARY KEY, imported_at TEXT, source TEXT, description TEXT, amount REAL)"""
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS imported_transactions (
                    tx_key TEXT PRIMARY KEY,
                    imported_at TEXT,
                    source TEXT,
                    description TEXT,
                    amount REAL
                )
                """
            )
            conn.commit()

    def _make_tx_key(self, tx) -> str:
        return f"{tx.date.date()}|{abs(tx.second_amount):.2f}|{tx.type.value}|{tx.id}"

    def mark_imported(self, transactions: list) -> None:
        """Store transaction keys as imported."""
        if not transactions:
            return
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO imported_transactions (tx_key, imported_at, source, description, amount) VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        self._make_tx_key(tx),
                        now,
                        tx.source or "",
                        tx.description or "",
                        float(abs(tx.second_amount)),
                    )
                    for tx in transactions
                ],
            )
            conn.commit()

    def filter_already_imported(self, transactions: list) -> list:
        """Return only transactions NOT already in the DB."""
        if not transactions:
            return []
        with sqlite3.connect(self.db_path) as conn:
            existing = {
                row[0]
                for row in conn.execute("SELECT tx_key FROM imported_transactions").fetchall()
            }
        return [tx for tx in transactions if self._make_tx_key(tx) not in existing]

    def get_stats(self) -> dict:
        """Return {'total_imported': N, 'first_import': '...', 'last_import': '...'}"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*), MIN(imported_at), MAX(imported_at) FROM imported_transactions"
            ).fetchone()
        return {
            "total_imported": row[0] if row else 0,
            "first_import": row[1] if row else None,
            "last_import": row[2] if row else None,
        }

    def clear(self) -> None:
        """Clear all state (for testing/reset)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM imported_transactions")
            conn.commit()
