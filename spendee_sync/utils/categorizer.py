from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from ..models import Transaction


def _compile_keyword_patterns(category_to_keywords: dict[str, list[Any]]) -> list[tuple[re.Pattern, str]]:
    """Compile keyword lists into regex patterns for fast matching.

    Args:
        category_to_keywords: {"Category": ["keyword1", "keyword2", ...]}

    Returns:
        List of (compiled_pattern, category) tuples
    """
    patterns: list[tuple[re.Pattern, str]] = []
    for category, words in category_to_keywords.items():
        if not isinstance(words, list) or not words:
            continue

        # Normalize and filter keywords
        normalized = [str(w).strip().lower() for w in words if isinstance(w, (str, bytes))]
        normalized = [w for w in normalized if w]
        if not normalized:
            continue

        # Build regex pattern with word boundaries
        escaped = [re.escape(w) for w in normalized]
        pattern = rf"\b(?:{'|'.join(escaped)})\b"
        compiled = re.compile(pattern, re.IGNORECASE)
        patterns.append((compiled, category))

    return patterns


def load_rules_from_env() -> tuple[dict[str, list[int]], list[tuple[re.Pattern, str]]]:
    """Load categorization rules from JSON file.

    Loads from CATEGORIZATION_RULES_JSON env variable.

    Supported formats:
    1. Unified: {"Category": {"mcc": [...], "keywords": [...]}}
    2. MCC only: {"Category": [mcc1, mcc2, ...]}
    3. Keywords only: {"Category": [keyword1, keyword2, ...]}

    Returns:
        Tuple of (mcc_rules, keyword_patterns) where:
        - mcc_rules: {"Category": [mcc_codes]}
        - keyword_patterns: [(compiled_regex, category)]
    """
    rules_path = os.getenv("CATEGORIZATION_RULES_JSON")
    if not rules_path or not os.path.exists(rules_path):
        return {}, []

    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}, []

        mcc_rules: dict[str, list[int]] = {}
        keyword_data: dict[str, list[str]] = {}

        # Check if it's the unified format (dict values with mcc/keywords keys)
        first_value = next(iter(data.values()), None) if data else None

        if isinstance(first_value, dict):
            # Unified format: {"Category": {"mcc": [...], "keywords": [...]}}
            for category, rules in data.items():
                if not isinstance(rules, dict):
                    continue

                # Extract MCC codes
                mcc_list = rules.get("mcc", [])
                if isinstance(mcc_list, list) and mcc_list:
                    mcc_rules[category] = [int(code) for code in mcc_list if isinstance(code, (int, str))]

                # Extract keywords
                kw_list = rules.get("keywords", [])
                if isinstance(kw_list, list) and kw_list:
                    keyword_data[category] = kw_list

            keyword_patterns = _compile_keyword_patterns(keyword_data)
            return mcc_rules, keyword_patterns

        elif isinstance(first_value, list):
            # Legacy format: detect if MCC or keywords by checking first element
            if not first_value:
                return {}, []

            sample = first_value[0] if first_value else None
            if isinstance(sample, int) or (isinstance(sample, str) and sample.isdigit()):
                # MCC format
                mcc_rules = {
                    cat: [int(code) for code in codes if isinstance(code, (int, str))]
                    for cat, codes in data.items()
                    if isinstance(codes, list)
                }
                return mcc_rules, []
            else:
                # Keyword format
                keyword_patterns = _compile_keyword_patterns(data)
                return {}, keyword_patterns

        return {}, []

    except Exception:
        return {}, []


def load_labels_from_file() -> dict[str, list[str]]:
    path = Path(__file__).parent / "labels_keywords.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        labels: dict[str, list[str]] = {}
        if isinstance(data, dict):
            for label, words in data.items():
                if isinstance(words, list):
                    labels[str(label)] = [str(w).lower() for w in words if isinstance(w, (str, bytes))]
        return labels
    except Exception:
        return {}


def assign_labels(note: str, labels_rules: dict[str, list[str]]) -> list[str]:
    """Assign labels to a note based on the labels rules."""
    text = (note or "").lower()
    found: list[str] = []
    for label, words in labels_rules.items():
        if any(w and w in text for w in words):
            found.append(label)
    return found


def categorize_transaction(tx: Transaction, mcc_rules: dict[str, list[int]], keyword_patterns: list[tuple[re.Pattern, str]]) -> Transaction:
    """Categorize a transaction based on MCC codes and keywords.

    Categorization priority:
    1. MCC code lookup
    2. Keyword pattern matching
    3. Fallback based on amount sign (Income/Other)

    Args:
        tx: Transaction to categorize

    Returns:
        Transaction with category field populated
    """

    # 2) Try keyword pattern matching
    if keyword_patterns:
        description = (tx.description or "").lower()
        for pattern, category in keyword_patterns:
            if pattern.search(description):
                return tx.copy(update={"category": category})

    # 1) Try MCC code lookup
    if tx.mcc and mcc_rules:
        for category, mcc_codes in mcc_rules.items():
            if tx.mcc in mcc_codes:
                return tx.copy(update={"category": category})

    # 3) Fallback based on amount sign
    fallback = "Income" if tx.uah_amount > 0 else "Other"
    return tx.copy(update={"category": fallback})
