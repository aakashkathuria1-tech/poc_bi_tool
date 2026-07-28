# poc_bi_tool

Proof-of-concept BI tool for sales performance reporting: actual transactions
against monthly targets, sliced by region, manager, product category and time.

**Current state:** the repo holds the sample dataset and the local
environment setup. The application itself has not been written yet.

## Quick start (Windows)

```powershell
git clone https://github.com/aakashkathuria1-tech/poc_bi_tool.git
cd poc_bi_tool
.\scripts\setup.ps1
```

That installs Python dependencies into `.venv\` and runs a health check over
the data. Full instructions, including prerequisites and troubleshooting, are
in **[docs/windows-setup.md](docs/windows-setup.md)**.

If PowerShell blocks the script, either allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, or run
the `cmd.exe` fallback `scripts\setup.bat`.

## Quick start (macOS / Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/verify_data.py
```

## Repo layout

```
test_trans_data.csv       100,338 order lines, Jan 2024 - Dec 2026
test_month_targets.csv    2,100 monthly targets, Apr 2024 - Dec 2025
test_cust_master.csv      10 customers with region / city / manager
test_product_master.csv   10 products with category / sub-category
scripts/setup.ps1         Windows environment setup (PowerShell)
scripts/setup.bat         Windows environment setup (cmd.exe fallback)
scripts/verify_data.py    Loads the CSVs and reports on their health
docs/windows-setup.md     Full Windows guide + data dictionary
```

## The data

Ten customers across four regions, ten products across four categories, three
years of transactions, and two years of monthly targets at the
customer-x-product grain.

The CSVs came out of Excel and carry the artefacts to prove it. Before
building anything on them, read the
[data notes](docs/windows-setup.md#data-notes) - the two that will bite first:

- **`Date` is an Excel serial number** (45292-46386), not a date string.
  Convert using an 1899-12-30 origin.
- **IDs are padded inconsistently.** Masters say `C010`, transactions and
  targets say `C0010`. Joining without normalizing silently drops the 10th
  customer and the 10th product.

`scripts/verify_data.py` handles both, plus the trailing unnamed column and
the blank final row, and prints a summary you can sanity-check against:

```
100,338 rows, dates 2024-01-01 to 2026-12-30
gross          302,208,196
net            287,055,219
units              300,913
```

## Requirements

Python 3.10 or newer. Dependencies are pinned in `requirements.txt`.
