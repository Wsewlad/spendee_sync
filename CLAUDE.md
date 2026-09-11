# spendee_sync

Syncs Monobank (and Wise) transactions into Spendee: fetches transactions,
categorizes them, diffs them against a Spendee export to find what's
missing, and exports the result (CSV/XLSX) or imports it via optional
Selenium browser automation.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

Requires a `.env` file (never commit it) with `MONOBANK_TOKEN`, `IBAN`,
`CARD_TYPE`, and optionally `SPENDEE_EMAIL` / `SPENDEE_PASSWORD` /
`CATEGORIZATION_RULES_JSON` / `WALLET_NAME` — see `README.md` for details.

## Commands

```bash
pytest                       # run tests
black spendee_sync/ tests/   # format
black --check spendee_sync/ tests/   # verify formatting (CI)
flake8 spendee_sync/ tests/   # lint (config: .flake8)
python -m spendee_sync.task   # run the sync (configure task.py first)
```

## Layout

- `spendee_sync/models/` — `Transaction` (pydantic) and related types
- `spendee_sync/services/` — `monobank.py`, `wise.py`, `spendee.py`
  (fetch/parse/export/import)
- `spendee_sync/utils/` — `categorizer.py` (MCC/keyword rules),
  `diff_engine.py` (dedup by date/amount/type)
- `spendee_sync/task.py` — main entry point / example workflow
- `tests/` — pytest tests (mirrors `spendee_sync/` layout as it grows)

## Conventions

- Never commit `.env` or any real Monobank/Spendee credentials.
- Work on a feature branch and open a PR — no direct pushes to `main`.
  CI (`pytest`, `flake8`, `black --check`) must be green before merging.
- Match existing style: `black` (line length 100), type hints, pydantic
  models for data, `tenacity` for retries on external API calls.
- New behavior in `services/` or `utils/` should come with a test in
  `tests/`.
