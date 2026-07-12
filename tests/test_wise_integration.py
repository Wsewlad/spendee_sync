from __future__ import annotations

import os

import pytest

from spendee_sync.services.wise import WiseService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("WISE_TOKEN"),
        reason="requires WISE_TOKEN in the environment/.env",
    ),
]


def test_resolves_profile_id():
    service = WiseService()
    assert service.profile_id


def test_fetch_transactions_recent_window():
    service = WiseService()
    transactions = service.fetch_transactions(days=7)
    assert isinstance(transactions, list)
