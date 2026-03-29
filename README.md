# Splitwise YNAB Automator

Syncs your Splitwise debts to YNAB as split transactions. For each borrowed expense you can review the amount and assign a category before it is submitted to your budget.

## Features

- Fetches borrowed expenses from Splitwise since a configurable start date
- Deduplicates recurring expenses using content hashing — re-stamps are skipped, genuine edits are re-synced
- Handles multiple payers by splitting your share proportionally across all net creditors
- Per-expense review UI: accept or skip each expense and optionally assign a YNAB category
- Deletes the original YNAB transaction before re-submitting an edited expense (no duplicates)
- All submitted transactions are marked unapproved in YNAB so they appear in the "To Be Approved" queue

## Requirements

- macOS with [Homebrew](https://brew.sh)
- Python 3.13
- Splitwise API credentials
- YNAB personal access token

## Setup

### 1. Install Python 3.13 and tkinter support

```bash
brew install python@3.13 python-tk@3.13
```

> `python-tk@3.13` is a separate Homebrew formula. Without it the GUI will fail with `ModuleNotFoundError: No module named 'tkinter'`.

### 2. Clone the repository

```bash
git clone <repo-url>
cd Splitwise-YNAB-Automator
```

### 3. Create and activate the virtual environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure credentials

Edit `config/config.yaml`:

```yaml
splitwise_api:
  consumer_key: <your-consumer-key>
  consumer_secret: <your-consumer-secret>
  api_key: <your-api-key>
  expenses:
    user_name: <your-first-name-as-in-splitwise>
    from_date: 2024-01-01

ynab_api:
  token: <your-ynab-personal-access-token>
  budget_id: <your-budget-id>
  account_id: <your-account-id>
  categories:
    - inflow_default_category: "Friends Reimbursements"
      category_id: <your-reimbursement-category-id>
```

- Splitwise credentials: [Splitwise Apps](https://secure.splitwise.com/apps)
- YNAB token: YNAB → Account Settings → Developer Settings → New Token
- `budget_id` and `account_id`: visible in the YNAB web app URL or via the YNAB API
- `inflow_default_category`: the YNAB category used for the reimbursement inflow subtransaction

## Usage

### GUI (recommended)

```bash
python src/main_gui.py
```

### CLI

```bash
python src/main.py
```

## Running tests

```bash
python -m pytest tests/
```

## Project structure

```
config/
  config.yaml          # API credentials and user settings
src/
  main_gui.py          # GUI entry point (FreeSimpleGUI)
  main.py              # CLI entry point
  splitwise_expenses.py
  ynab_expenses.py
  read_yaml_config.py
  get_latest_timestamp_for_user.py
tests/
output/                # Generated CSV exports and processed_expenses_<user>.json
requirements.txt
```
