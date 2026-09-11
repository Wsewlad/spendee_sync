from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Tuple, Any
import re

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from spendee_sync.models.transaction import Transaction, TransactionType
from spendee_sync.utils.categorizer import load_labels_from_file, assign_labels

# Wise public API base; can be overridden for sandbox via env
WISE_API = os.getenv("WISE_API", "https://api.transferwise.com")


class WiseService:
    def __init__(self, token: Optional[str] = None, profile_id: Optional[str] = None) -> None:
        self.token = token or os.getenv("WISE_TOKEN")
        if not self.token:
            raise ValueError("WISE_TOKEN is required. Set it in environment or .env file.")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            }
        )
        self.profile_id = (
            profile_id or os.getenv("WISE_PROFILE_ID") or self._resolve_default_profile_id()
        )
        self.account_id = os.getenv("WISE_ACCOUNT_ID")  # optional; used for statements if needed

    @retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
    def _get(self, path: str, **params) -> Any:
        resp = self.session.get(f"{WISE_API}{path}", params=params, timeout=30)
        resp.raise_for_status()
        # Some Wise endpoints return empty body with 204; guard accordingly
        return resp.json() if resp.content else None

    def _resolve_default_profile_id(self) -> str:
        """
        Resolve a default profile id if not provided via env.
        Prefers 'personal' profile when available, otherwise first profile.
        """
        try:
            profiles = self._get("/v2/profiles")  # returns list of profiles
            if not profiles:
                raise ValueError("Wise: no profiles available for token")
            personal = [p for p in profiles if p.get("type") == "personal"]
            chosen = (personal[0] if personal else profiles[0]) or {}
            pid = chosen.get("id")
            if not pid:
                raise ValueError("Wise: failed to resolve profile id")
            return str(pid)
        except Exception as exc:
            raise ValueError(
                f"WISE_PROFILE_ID is required and could not be resolved automatically: {exc}"
            )

    @staticmethod
    def _strip_format_tags(text: str) -> str:
        """
        Wise Activity 'title' can include tags like <strong>, <positive>, <negative>.
        Strip all <...> tags and collapse whitespace.
        """
        if not text:
            return ""
        no_tags = re.sub(r"<[^>]*>", "", text)
        return re.sub(r"\s+", " ", no_tags).strip()

    @staticmethod
    def _parse_amount_field(amount_field: Any) -> Tuple[Decimal, str]:
        """
        Parse Wise 'primaryAmount' / 'secondaryAmount' which can appear either as:
        - object: {'value': '150.00', 'currency': 'JPY'} or {'value': 150, 'currency': 'JPY'}
        - string: '150 JPY' or '-150.22 USD'
        Returns (amount_decimal, currency_code).
        """
        if amount_field is None:
            return Decimal("0"), ""
        if isinstance(amount_field, dict):
            value = amount_field.get("value", 0)
            currency = str(amount_field.get("currency") or "").upper()
            try:
                return Decimal(str(value)), currency
            except Exception:
                return Decimal("0"), currency
        # Assume string like "150 JPY" or "-12.34 USD"
        if isinstance(amount_field, str):
            parts = amount_field.strip().rsplit(" ", 1)
            if len(parts) == 2:
                value_str, currency = parts
                try:
                    return Decimal(value_str.replace(",", "")), currency.upper()
                except Exception:
                    return Decimal("0"), currency.upper()
        # Fallback
        try:
            return Decimal(str(amount_field)), ""
        except Exception:
            return Decimal("0"), ""

    def _parse_activity_to_transaction(self, activity: dict) -> Transaction:
        """
        Convert a Wise Activity item to our Transaction model.
        """
        # Prefer createdOn; fallback to updatedOn
        created_on = activity.get("createdOn") or activity.get("updatedOn")
        if isinstance(created_on, str):
            # Normalize Zulu time
            created_on = created_on.replace("Z", "+00:00")
            dt = datetime.fromisoformat(created_on)
        else:
            # If missing or invalid, use now in UTC
            dt = datetime.now(timezone.utc)

        title = self._strip_format_tags(activity.get("title") or "")
        description = activity.get("description") or ""
        full_description = (
            title if not description else f"{title}: {description}".strip(": ").strip()
        )

        primary_amount_raw = activity.get("primaryAmount")
        primary_value, primary_currency = self._parse_amount_field(primary_amount_raw)

        secondary_amount_raw = activity.get("secondaryAmount")
        secondary_value, secondary_currency = self._parse_amount_field(secondary_amount_raw)

        # Determine secondary amount if available via secondary amount, otherwise keep primary
        second_amount = primary_value
        if secondary_currency:
            second_amount = secondary_value
        elif primary_currency:
            second_amount = primary_value

        tx_type = TransactionType.INCOME if primary_value >= 0 else TransactionType.EXPENSE

        # Use resource id or env account id as account reference
        resource = activity.get("resource") or {}
        account_id = self.account_id or str(resource.get("id") or self.profile_id)

        # Load label rules once per instance
        # (Monobank loads on each fetch; keep symmetry)
        if not hasattr(self, "_label_rules"):
            self._label_rules = load_labels_from_file()
        labels_list = assign_labels(full_description, self._label_rules)

        return Transaction(
            id=str(activity.get("id") or ""),
            date=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc),
            primary_amount=(
                primary_value.copy_abs().copy_negate()
                if primary_value.is_signed()
                else primary_value
            ),
            second_amount=(
                second_amount.copy_abs().copy_negate()
                if second_amount.is_signed()
                else second_amount
            ),
            currency=primary_currency or "",
            mcc=0,
            description=full_description,
            comment="",
            labels=labels_list or None,
            type=tx_type,
            account_id=str(account_id),
            wallet=None,
            category=None,
            source="wise",
            raw=activity,
        )

    def fetch_activities(
        self, days: int = 30, limit: int = 250, max_pages: Optional[int] = None
    ) -> list[dict]:
        """
        Fetch Wise activities for the profile.
        Supports Wise pagination via 'cursor' and response shapes:
        - {'activities': [...], 'cursor': '...'}
        - {'items': [...], 'next': '...'}
        - or a plain list
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        path = f"/v1/profiles/{self.profile_id}/activities"

        def _normalize_page(payload: Any) -> tuple[list[dict], Optional[str]]:
            if isinstance(payload, list):
                return payload, None
            if isinstance(payload, dict):
                if "activities" in payload:
                    return payload.get("activities", []) or [], payload.get("cursor") or None
                if "items" in payload:
                    return payload.get("items", []) or [], payload.get("next") or None
            return [], None

        collected: list[dict] = []
        seen_ids: set[str] = set()
        cursor: Optional[str] = None

        # initial params (createdOnStart may be ignored by the API, harmless if so)
        base_params: dict[str, Any] = {
            "limit": limit,
            "createdOnStart": since.replace(microsecond=0).isoformat(),
        }

        while True:
            params = {"limit": limit}
            params.update({"cursor": cursor} if cursor else base_params)

            data = self._get(path, **params) or {}
            page_items, next_cursor = _normalize_page(data)
            if not page_items:
                break

            new_items: list[dict] = []
            for it in page_items:
                it_id = str(it.get("id") or "")
                if it_id and it_id in seen_ids:
                    continue
                if it_id:
                    seen_ids.add(it_id)
                new_items.append(it)

            if not new_items:
                break

            collected.extend(new_items)

            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return collected

    def fetch_transactions(self, days: int = 30) -> list[Transaction]:
        """
        Produce Transaction objects from Wise activities.
        """
        raw_activities = self.fetch_activities(days=days)
        transactions: list[Transaction] = []
        for item in raw_activities:
            try:
                transactions.append(self._parse_activity_to_transaction(item))
            except Exception:
                # Skip malformed activity records
                continue
        return transactions


def main() -> None:
    service = WiseService()
    txs = service.fetch_transactions(days=30)
    print(txs)


if __name__ == "__main__":
    main()
