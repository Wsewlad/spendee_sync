"""In-memory session state and JSON sidecar persistence for the dashboard."""
from __future__ import annotations

import csv
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Path to the sidecar file that stores edited overrides
STATE_FILE = Path("dashboard_state.json")
# Path where the main sync writes missing transactions
MISSING_CSV = Path("spendee_sync/outputs/missing_for_spendee.csv")

_lock = threading.Lock()

# In-memory store: list of transaction dicts (as loaded from CSV)
_transactions: List[Dict] = []
# Overrides keyed by transaction id: {"category": ..., "labels": ...}
_overrides: Dict[str, Dict] = {}
_last_sync: Optional[str] = None  # ISO datetime string
_sync_in_progress: bool = False


def _load_state_file() -> None:
    """Load persisted overrides and last_sync from the sidecar JSON file."""
    global _overrides, _last_sync
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            _overrides = data.get("overrides", {})
            _last_sync = data.get("last_sync", None)
        except Exception:
            _overrides = {}
            _last_sync = None


def _save_state_file() -> None:
    """Persist overrides and last_sync to the sidecar JSON file."""
    data = {"overrides": _overrides, "last_sync": _last_sync}
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_transactions_from_csv() -> None:
    """Read pending transactions from the missing CSV and store them in memory."""
    global _transactions
    rows: List[Dict] = []
    if MISSING_CSV.exists():
        with open(MISSING_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                # Assign a stable id based on row index (CSV has no id column)
                row_id = f"tx_{i}"
                rows.append({
                    "id": row_id,
                    "date": row.get("Date", ""),
                    "type": row.get("Type", ""),
                    "category": row.get("Category name", ""),
                    "amount": row.get("Amount", ""),
                    "description": row.get("Note", ""),
                    "labels": row.get("Labels", ""),
                })
    with _lock:
        _transactions = rows


def get_transactions() -> List[Dict]:
    """Return a snapshot of pending transactions with overrides applied."""
    with _lock:
        result = []
        for tx in _transactions:
            merged = dict(tx)
            override = _overrides.get(tx["id"], {})
            if "category" in override:
                merged["category"] = override["category"]
            if "labels" in override:
                merged["labels"] = override["labels"]
            result.append(merged)
        return result


def apply_override(tx_id: str, category: Optional[str], labels: Optional[str]) -> bool:
    """Apply a category/labels override for a transaction. Returns False if tx not found."""
    with _lock:
        ids = {tx["id"] for tx in _transactions}
        if tx_id not in ids:
            return False
        if tx_id not in _overrides:
            _overrides[tx_id] = {}
        if category is not None:
            _overrides[tx_id]["category"] = category
        if labels is not None:
            _overrides[tx_id]["labels"] = labels
        _save_state_file()
        return True


def get_last_sync() -> Optional[str]:
    with _lock:
        return _last_sync


def set_last_sync(dt: Optional[str]) -> None:
    global _last_sync
    with _lock:
        _last_sync = dt
        _save_state_file()


def is_sync_in_progress() -> bool:
    with _lock:
        return _sync_in_progress


def set_sync_in_progress(value: bool) -> None:
    global _sync_in_progress
    with _lock:
        _sync_in_progress = value


def get_summary() -> Dict:
    """Return a summary dict: total count and categories breakdown."""
    txs = get_transactions()
    categories: Dict[str, int] = {}
    for tx in txs:
        cat = tx.get("category") or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total": len(txs),
        "categories": categories,
        "last_sync": get_last_sync(),
    }


# Bootstrap: load persisted state on module import
_load_state_file()
load_transactions_from_csv()
