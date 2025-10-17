# Spendee Sync

Automatically sync your Monobank transactions to Spendee with smart categorization, deduplication, and optional browser automation for seamless imports.

## Features

- 🏦 **Monobank Integration** - Fetches transactions directly from Monobank API (supports 90+ days with automatic chunking)
- 🏷️ **Smart Categorization** - Automatically categorizes transactions based on MCC codes and keywords (priority: keywords → MCC → fallback)
- 🏷️ **Auto-Labeling** - Intelligent label assignment based on merchant names
- 🔄 **Intelligent Diff Engine** - Identifies missing transactions by comparing Monobank and Spendee exports
- 📊 **Multiple Export Formats** - Supports CSV and JSON output formats
- 🔍 **Comparison Reports** - Side-by-side comparison of existing transactions showing differences in categories and labels
- 💱 **Multi-Currency Support** - Displays original amounts with exchange rates in transaction notes
- 🤖 **Browser Automation** - Optional Selenium-based automatic import into Spendee
- ⚙️ **Customizable Rules** - Unified JSON configuration for both MCC codes and keyword-based categorization

## Prerequisites

- Python 3.10 or higher
- Monobank API token (get it from the Monobank app)
- Spendee account (for automated import feature)

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd spendee_sync
```

### 2. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install the package

```bash
pip install -U pip
pip install -e .
```

## Configuration

Create a `.env` file in the project root with the following variables:

### Required Variables

```bash
# Monobank API token (get from Monobank mobile app)
MONOBANK_TOKEN=your_monobank_token_here

# Your bank account IBAN (without spaces)
IBAN=UA123456789012345678901234567

# Card/Account type (e.g., "black", "white", "fop")
CARD_TYPE=black
```

### Optional Variables

```bash
# Spendee credentials (required only for automated browser import)
SPENDEE_EMAIL=your.email@example.com
SPENDEE_PASSWORD=your_secure_password

# Custom categorization rules file path
CATEGORIZATION_RULES_JSON=path/to/your/rules.json

# Default wallet name for imports
WALLET_NAME=Main Wallet
```

## Usage

### Basic Workflow

The typical workflow consists of three steps:

1. **Export** your current Spendee transactions from the Spendee app/web (as CSV)
2. **Run** the sync script to fetch Monobank transactions and find missing ones
3. **Import** the missing transactions back into Spendee (manual or automated)

### Running the Sync

#### Option 1: Using the Python script directly

```bash
# Edit spendee_sync/task.py to configure:
# - days: number of days to look back (default: 30)
# - spendee_xlsx: path to your Spendee export file
# - out_path: where to save missing transactions

python -m spendee_sync.task
```

#### Option 2: Using individual services

```python
from dotenv import load_dotenv
from spendee_sync.services.monobank import MonobankService
from spendee_sync.services.spendee import SpendeeService
from spendee_sync.utils.categorizer import categorize_transaction
from spendee_sync.utils.diff_engine import compute_missing

load_dotenv()

# Fetch Monobank transactions
mono = MonobankService()
mono_txs = [categorize_transaction(t) for t in mono.fetch_transactions(days=60)]

# Parse Spendee export
spendee = SpendeeService()
spendee_txs = spendee.parse_export("path/to/spendee_export.csv")

# Find missing transactions
missing = compute_missing(mono_txs, spendee_txs)
missing = [categorize_transaction(t) for t in missing]

# Export to CSV
spendee.export_csv(missing, "missing_transactions.csv")

# Or export to XLSX
# spendee.export_xlsx(missing, "missing_transactions.xlsx")
```

### Automated Browser Import

To automatically import transactions into Spendee using Selenium:

```python
from spendee_sync.services.spendee import SpendeeService

spendee = SpendeeService()
spendee.import_file(
    filepath="missing_transactions.csv",
    email="your@email.com",           # Optional if set in .env
    password="your_password",          # Optional if set in .env
    wallet_name="Main Wallet",         # Optional
    headless=True                      # Run browser in headless mode
)
```

## Categorization System

### How It Works

Transactions are automatically categorized using:
1. **MCC (Merchant Category Code)** - Standard banking industry codes
2. **Keyword matching** - Based on transaction description
3. **Custom rules** - Your own categorization logic

### Custom Categorization Rules

Create a JSON file with custom rules:

```json
{
  "rules": [
    {
      "keywords": ["uber", "bolt", "taxi"],
      "category": "Transport",
      "labels": ["taxi", "ride-sharing"]
    },
    {
      "keywords": ["amazon", "rozetka"],
      "category": "Shopping",
      "labels": ["online-shopping"]
    },
    {
      "mcc": [5411, 5412],
      "category": "Groceries",
      "labels": ["food", "supermarket"]
    }
  ]
}
```

Then reference it in your `.env`:

```bash
CATEGORIZATION_RULES_JSON=path/to/custom_rules.json
```

## Output Format

### CSV/XLSX Columns

The exported file includes the following columns compatible with Spendee import:

- **Date** - Transaction date in ISO 8601 format
- **Wallet** - Wallet name (optional)
- **Type** - Transaction type (INCOME or EXPENSE)
- **Category name** - Auto-assigned or custom category
- **Amount** - Transaction amount in decimal format
- **Currency** - Currency code (UAH, USD, EUR, etc.)
- **Note** - Transaction description
- **Labels** - Comma-separated labels for better organization
- **Author** - (optional)

## Project Structure

```
spendee_sync/
├── models/           # Data models (Transaction, etc.)
├── services/         # Core services
│   ├── monobank.py  # Monobank API integration
│   └── spendee.py   # Spendee export/import logic
├── utils/            # Utility functions
│   ├── categorizer.py   # Transaction categorization
│   └── diff_engine.py   # Transaction comparison logic
├── inputs/           # Input files (Spendee exports)
├── outputs/          # Generated output files
└── task.py          # Main execution script
```

## Troubleshooting

### Common Issues

**Error: "MONOBANK_TOKEN is required"**
- Make sure you've created a `.env` file with your Monobank token
- Get your token from the Monobank mobile app (Settings → API)

**Error: "Account with IBAN not found"**
- Verify your `IBAN` and `CARD_TYPE` are correct in `.env`
- Check available accounts by printing `mono.get_client_info()`

**Selenium browser automation fails**
- Ensure Chrome/Chromium is installed
- Check if `SPENDEE_EMAIL` and `SPENDEE_PASSWORD` are correct
- Try running without `headless=True` to see what's happening

**Duplicate transactions after import**
- The diff engine compares by date, amount, and description
- If duplicates appear, check if your Spendee export includes all transactions

**Categorization not working**
- Check if your `CATEGORIZATION_RULES_JSON` file is valid JSON
- Verify the file path is correct and accessible

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (if available)
pytest
```

### Code Formatting

```bash
# Format code with black
black spendee_sync/

# Check code style
flake8 spendee_sync/
```

## Technical Details

### Currency Conversion

- Monobank returns amounts in minor currency units (kopiykas for UAH)
- Amounts are automatically divided by 100 and formatted to 2 decimal places
- Multi-currency transactions show both original and UAH amounts

### Transaction Matching

The diff engine identifies duplicates using:
- Transaction date (with timezone normalization)
- Amount (exact match)
- Description/note (similarity matching)

### API Rate Limits

Monobank API has rate limits:
- 1 request per 60 seconds for personal token
- Built-in retry logic with exponential backoff

## Security Notes

- Never commit your `.env` file with real credentials
- Keep your Monobank token secure - it provides full access to your account data
- Consider using environment variables instead of `.env` in production

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review existing GitHub issues
3. Create a new issue with detailed information about your problem

## Roadmap

- [ ] CLI interface with argparse/click
- [ ] Support for multiple bank accounts
- [ ] Web dashboard for transaction review
- [ ] Support for more banking APIs
- [ ] Machine learning-based categorization
- [ ] Docker containerization
