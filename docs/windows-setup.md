# Windows setup guide

Getting `poc_bi_tool` running on a Windows machine, from a clean box.

Tested target: Windows 10 or 11, Python 3.10+. Everything below is
PowerShell unless a `cmd.exe` alternative is called out.

---

## 1. Install the prerequisites

### Git

```powershell
winget install Git.Git
```

Or download from <https://git-scm.com/download/win>.

During install (or afterwards, via `git config`), leave **"Checkout as-is,
commit as-is"** or set the equivalent:

```powershell
git config --global core.autocrlf false
```

This repo ships a `.gitattributes` that pins line endings per file type, so
the global setting mostly does not matter - but `core.autocrlf true` on a
repo whose CSVs are already committed with CRLF is a recipe for confusing
whole-file diffs.

### Python

```powershell
winget install Python.Python.3.12
```

Or download from <https://www.python.org/downloads/windows/> and **tick
"Add python.exe to PATH"** in the installer.

Then **close and reopen your terminal** so the new PATH is picked up.

Confirm:

```powershell
py --version
```

> If this opens the Microsoft Store instead of printing a version, Windows is
> intercepting the command with an App Execution Alias. Turn it off:
> **Settings > Apps > Advanced app settings > App execution aliases**, then
> switch off both `python.exe` and `python3.exe`.

---

## 2. Clone the repo

```powershell
cd $HOME\projects        # or wherever you keep code
git clone https://github.com/aakashkathuria1-tech/poc_bi_tool.git
cd poc_bi_tool
```

The transaction CSV is ~6 MB, so a clone takes a moment but needs no Git LFS.

> **Path length:** if you clone deep inside `C:\Users\...\OneDrive\...`, you
> can hit the 260-character path limit once a `.venv` is nested inside. A
> short path such as `C:\dev\poc_bi_tool` avoids the problem entirely.

> **OneDrive:** avoid cloning into a synced OneDrive folder. Sync will fight
> the venv over thousands of small files, and file locks cause intermittent
> pip failures.

---

## 3. Run the setup script

```powershell
.\scripts\setup.ps1
```

This creates `.venv\`, installs `requirements.txt` into it, runs the tests, and
runs the data health check. It is safe to re-run; pass `-Force` to rebuild the
venv from scratch, or `-SkipVerify` to skip the tests and health check.

### If PowerShell refuses to run the script

You will see *"running scripts is disabled on this system"*. Allow locally
authored scripts for your own user (this does not require admin):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then re-run `.\scripts\setup.ps1`.

If your organisation locks execution policy by Group Policy and you cannot
change it, use the `cmd.exe` fallback instead:

```bat
scripts\setup.bat
```

### Doing it by hand

The scripts are a convenience, not a requirement:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
pytest
python scripts\verify_data.py
```

---

## 4. Run the dashboard

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

It opens at <http://localhost:8501>. Stop it with `Ctrl+C`.

> The first launch may prompt for an email address — that is Streamlit's
> optional telemetry prompt. Press Enter to skip it. To silence it for good,
> create `.streamlit\config.toml` with:
> ```toml
> [browser]
> gatherUsageStats = false
> ```

> **Windows Firewall** may show a prompt the first time. Streamlit only needs
> to listen on localhost, so you can safely decline public-network access.

---

## 5. Daily use

Activate the environment in each new terminal:

```powershell
.\.venv\Scripts\Activate.ps1     # PowerShell
.venv\Scripts\activate.bat       # cmd.exe
```

Your prompt gains a `(.venv)` prefix. Deactivate with `deactivate`.

Then:

```powershell
streamlit run app.py             # dashboard
pytest                           # 43 tests
python scripts\verify_data.py    # data health check
python scripts\export_clean.py   # clean data -> output\poc_bi_clean.xlsx
```

The health check should report
`PASSED - environment and data are usable (2 warning(s))`. The two warnings
are known properties of the sample data, described in [Data notes](#data-notes)
below.

### Exporting for Power BI or Excel

`scripts\export_clean.py` writes the cleaned, joined fact table plus
pre-built rollups. Point Power BI or Excel at its output rather than the raw
CSVs — the quirks below are already handled and the IDs already join.

```powershell
python scripts\export_clean.py                 # output\poc_bi_clean.xlsx
python scripts\export_clean.py --format csv    # one .csv per table
python scripts\export_clean.py --out C:\reports
```

---

## 6. VS Code (optional)

```powershell
winget install Microsoft.VisualStudioCode
code .
```

Install the **Python** extension, then `Ctrl+Shift+P` >
**Python: Select Interpreter** > choose `.\.venv\Scripts\python.exe`. VS Code
will then activate the venv automatically in new terminals.

---

## Data notes

The four CSVs in the repo root are the POC dataset. Anything reading them
needs to handle the following - `src/poc_bi/data.py` implements every fix, and
`tests/test_data.py` locks them in.

### The sample data is synthetic and has no signal

Measured, not assumed:

| Checked | Result |
| --- | --- |
| Customer share of revenue | C001-C010 all ~10.0% |
| Product share of revenue | P001-P010 all ~10.0% |
| Monthly revenue | CV 0.038 - no trend, no seasonality |
| `MRP` | ~1,978 distinct prices *per product* - not a price list |
| `Qty` / `Discount` | uniform 1-5 / uniform 0-0.10 |
| **`Target` vs actuals** | **correlation ~0.00** (qty -0.019, revenue 0.008) |

`Target` is uniform random in [100, 1000] with no relationship to the
transactions, so achievement lands near 15% and every month reads red. That
is a property of the generator, not a business finding. The dashboard carries
a banner saying so.

Use this data to exercise the tool - volume, joins, date handling, drill
paths - and swap in real extracts before drawing conclusions. Build a
`DataPaths` with your own file locations and nothing downstream changes.

### Files

| File | Grain | Rows |
| --- | --- | --- |
| `test_trans_data.csv` | one order line | 100,338 (+1 blank) |
| `test_month_targets.csv` | customer x product x month | 2,100 |
| `test_cust_master.csv` | customer | 10 |
| `test_product_master.csv` | product | 10 |

### Columns

**`test_trans_data.csv`** - `Cust_ID`, `Prod_ID`, `Date`, `Order No`,
`Item No`, `Qty`, `MRP`, `Cost`, `Discount`, plus an unnamed trailing column.

**`test_month_targets.csv`** - `Cust_ID`, `Prod_ID`, `Month`, `Target`.

**`test_cust_master.csv`** - `customer_id`, `region`, `city`, `area_manager`,
`zonal_manager`. Four regions (North/South/West/East), four zonal managers,
seven area managers.

**`test_product_master.csv`** - `product_id`, `category`, `sub_category`.
Four categories (Electronics/Home/Fashion/Auto).

### Quirks to handle

1. **`Date` is an Excel serial number, not a date.** Values run 45292 to
   46386. Convert with the Excel epoch of 1899-12-30:

   ```python
   pd.to_datetime(df["Date"], unit="D", origin="1899-12-30")
   ```

   That yields 2024-01-01 through 2026-12-30.

2. **IDs are zero-padded inconsistently across files.** The masters use
   `C001`..`C010` and `P001`..`P010`, but the transaction and target files
   use `C001`..`C009` plus **`C0010`** (and likewise `P0010`). A naive join
   silently drops the 10th customer and the 10th product. Normalize both
   sides before joining - strip the letter, parse the number, re-pad to three
   digits.

3. **The header of `test_trans_data.csv` has a trailing comma**, so pandas
   invents an `Unnamed: 9` column. It is a row counter; drop it.

4. **The last row of `test_trans_data.csv` is blank** except for that counter
   (`,,,,,,,,,5`). Drop all-null rows after load.

5. **Four duplicate `(Order No, Item No)` pairs** exist. Decide whether they
   are genuine repeats or data-entry noise before treating that pair as a
   primary key.

6. **Transactions extend past the target window.** Transactions cover Jan 2024
   - Dec 2026; targets only cover Apr 2024 - Dec 2025. About 59% of
   transactions fall inside the target window, so any actual-vs-target view
   must state its date filter or the comparison will look wrong.

7. **`Target` has no stated unit of measure.** It totals ~1.19M against
   ~301K total `Qty`, so it is unlikely to be units. Confirm with whoever
   produced the file before comparing it to anything.

8. **`Discount` is a fraction** (0.01 - 0.08 in the sample), not a
   percentage. `Cost` appears to be per-unit cost, and `MRP` per-unit list
   price - confirm before building margin logic on top of them.

---

## Troubleshooting

**`'py' is not recognized`** - Python is not installed or not on PATH. Reopen
the terminal after installing; if it still fails, re-run the installer and
choose *Modify > Add python.exe to PATH*.

**`Set-ExecutionPolicy` fails with "access denied"** - use `-Scope
CurrentUser` (as shown above), not the machine scope, which needs admin.

**pip fails with SSL / certificate errors** - usually a corporate TLS proxy.
Point pip at your proxy's CA bundle rather than disabling verification:
`pip config set global.cert C:\path\to\corp-ca.pem`.

**pip fails with "Access is denied" on a `.dll`** - antivirus or OneDrive has
the file locked. Close editors, exclude the repo folder from real-time
scanning, and re-run `.\scripts\setup.ps1 -Force`.

**`verify_data.py` reports missing data files** - run it from the repo root,
and confirm the four `.csv` files are present with `dir *.csv`.

**`streamlit` is not recognized** - the venv is not active. Either activate it
or call it by path: `.\.venv\Scripts\streamlit.exe run app.py`.

**Port 8501 already in use** - an earlier Streamlit is still running. Either
pick another port (`streamlit run app.py --server.port 8502`) or find and stop
the old one: `netstat -ano | findstr :8501` then `taskkill /PID <pid> /F`.

**`ModuleNotFoundError: No module named 'poc_bi'`** - run commands from the
repo root. `app.py` and the scripts add `src\` to the path themselves, and
pytest picks it up from `pyproject.toml`, but all of that is relative to the
repo root.

**`PermissionError` writing to `output\`** - the `.xlsx` is open in Excel.
Close it and re-run, or pass `--out` a different directory.

**Odd characters in the console output** - switch the terminal to UTF-8 with
`chcp 65001`, or use Windows Terminal, which defaults to it.
