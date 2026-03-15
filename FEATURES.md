# Spendee Sync — Feature Brainstorm & Improvements

## New Features

### 1. CLI Interface
Build a proper command-line interface using `click` or `argparse`.

```
spendee-sync fetch --source monobank --days 30
spendee-sync sync --dry-run
spendee-sync compare --output report.csv
spendee-sync categorize --rules custom_rules.json
```

Benefits: easier automation, scheduling via cron, clearer entry points per use case.

---

### 2. Multi-Account Support
Currently the sync assumes a single bank account. Allow users to define multiple accounts in config and sync all of them in one run.

```yaml
accounts:
  - name: Monobank Black
    type: monobank
    token: ${MONO_TOKEN_1}
  - name: Monobank White
    type: monobank
    token: ${MONO_TOKEN_2}
  - name: Wise EUR
    type: wise
    token: ${WISE_TOKEN}
```

---

### 3. Scheduled Sync (Daemon Mode)
Add a `--watch` mode or a scheduler (using `APScheduler` or `schedule`) that runs the sync automatically at a configurable interval (e.g., every hour).

This removes the need for external cron setup and allows the tool to run continuously as a background process.

---

### 4. Machine Learning Categorization
Supplement rule-based categorization with a local ML model trained on the user's own historical data.

- Export labeled transactions as training set
- Fine-tune a simple text classifier (e.g., scikit-learn TF-IDF + logistic regression, or a lightweight transformer)
- Fall back to rule-based if confidence is low

This improves accuracy over time, especially for ambiguous merchants.

---

### 5. Web Dashboard
A lightweight local web UI (using `FastAPI` + `Jinja2` or `Streamlit`) for:

- Reviewing pending transactions before import
- Manually correcting categories/labels
- Viewing sync history and stats
- Triggering syncs manually

This is more accessible than editing raw CSV files.

---

### 6. Interactive Transaction Review (TUI)
A terminal UI (using `textual` or `rich`) that lets users quickly review and correct categorizations before importing, without needing a browser. Faster than a web UI for power users.

---

### 7. Notification Support
Send a summary after each sync run via:
- Telegram bot message
- Email (SMTP)
- Desktop notification (via `plyer`)

Example: "Synced 12 new transactions. 2 need manual review."

---

### 8. Duplicate Detection Improvements
The current diff engine uses (date, amount, type) as a key. Improve this with:

- Fuzzy date matching (±1 day tolerance for timezone edge cases)
- Hash-based deduplication using a local SQLite cache of already-imported transaction IDs
- Detect near-duplicates (same amount, ±1 hour) to handle pending vs. settled transactions

---

### 9. More Bank Integrations
Expand beyond Monobank and Wise:

- **PrivatBank** (Ukraine) — popular alternative to Monobank
- **Revolut** — via their Open Banking API
- **Nordigen / GoCardless** — Open Banking aggregator that covers 2000+ European banks
- **OFX / QIF / MT940 file import** — for banks that only provide file exports

A plugin-style architecture (each bank = one file in `services/`) is already in place — just add more.

---

### 10. Category & Label Editor
A CLI or UI tool to interactively edit `categories.json` and `labels_keywords.json`:

- Add/remove/edit rules without touching raw JSON
- Preview which existing transactions would be affected by a rule change
- Export rules as a shareable preset

---

### 11. Transaction Notes Enrichment
Enhance transaction `notes` with additional context:

- Merchant logo / brand name lookup (via Clearbit or similar)
- Google Maps-style location link for POS transactions with location data
- Exchange rate history chart link for foreign currency transactions

---

### 12. Budget Tracking Integration
After syncing to Spendee, also post category totals to:

- A local budget config file (YAML/JSON)
- Google Sheets (via API)
- Notion database (via API)

Allow users to set monthly budget limits per category and get alerts when exceeded.

---

## Improvements to Existing Features

### A. Configuration Management
- Replace scattered `os.environ` calls with a single validated config class (Pydantic `BaseSettings`)
- Support a `config.yaml` or `.env` file with documented defaults
- Add a `spendee-sync init` command that interactively creates the config

### B. Error Handling & Resilience
- Better error messages when API tokens are missing or expired
- Graceful handling of Monobank rate limit errors (currently just sleeps 60s globally)
- Retry only failed time-chunk requests instead of restarting the whole fetch

### C. Logging
- Replace bare `print()` calls with structured logging (`logging` module or `structlog`)
- Support log levels (`--verbose`, `--quiet`)
- Optionally write logs to a file for debugging

### D. Test Coverage
- Unit tests for the categorizer (given a description + MCC, assert expected category)
- Unit tests for the diff engine (given two transaction lists, assert correct missing set)
- Integration test fixtures using recorded API responses (VCR cassettes via `vcrpy`)
- CI pipeline (GitHub Actions) that runs tests on push

### E. Packaging
- Add `pyproject.toml` with proper metadata and dependencies
- Publish to PyPI so users can `pip install spendee-sync`
- Add a `Dockerfile` for containerized usage

### F. Categorization Quality Metrics
After a comparison run, report:
- % of transactions matched by keyword vs. MCC vs. fallback
- % agreement between auto-categorization and existing Spendee categories
- List of uncategorized or low-confidence transactions for manual review

### G. Idempotent Imports
Track imported transaction IDs in a local SQLite or JSON state file so re-running the sync never creates duplicates, even if the diff engine has edge cases.

### H. Timezone Handling
Audit all datetime operations to ensure consistent UTC storage and correct local-time display in reports (currently mixed — some UTC, some local).

### I. Wise Integration Parity
The Wise service (`wise.py`) is less feature-complete than Monobank. Bring it to parity:
- Multi-currency balance support
- Correct MCC code mapping (Wise transactions don't always have MCC)
- Same comparison report format as Monobank

### J. Output File Management
- Auto-name output files with timestamp + account name (e.g., `mono_2026-03-15_sync.csv`)
- Option to upload output files directly to Google Drive or Dropbox
- Keep a local archive of all past export files
