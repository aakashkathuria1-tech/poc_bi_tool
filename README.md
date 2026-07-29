# poc_bi_tool

Proof-of-concept BI tool for sales performance reporting: actual transactions
against monthly targets, sliced by region, manager, product category and time.

## Quick start (Windows)

```powershell
git clone https://github.com/aakashkathuria1-tech/poc_bi_tool.git
cd poc_bi_tool
.\scripts\setup.ps1
.\.venv\Scripts\streamlit.exe run app.py
```

`setup.ps1` installs dependencies into `.venv\`, runs the tests, and health-checks
the data. Full instructions and troubleshooting: **[docs/windows-setup.md](docs/windows-setup.md)**.

If PowerShell blocks the script, either allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, or run
the `cmd.exe` fallback `scripts\setup.bat`.

## Work from your phone

To drive this machine from the Claude mobile app — code running on your
Windows PC, reaching your servers through it:

```powershell
.\scripts\setup_claude_code.ps1     # one time
.\scripts\start_remote_control.ps1  # each session
```

Then open the Claude app → **Code** tab and pick the session. Full guide,
including SSH/database access and viewing the dashboard from your phone:
**[docs/mobile-remote-control.md](docs/mobile-remote-control.md)**.

## Quick start (macOS / Linux)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## ⚠️ The sample data is synthetic and has no signal

Before anyone reads a conclusion off this dashboard: the shipped CSVs are
uniform random noise, not a realistic sales extract.

| Checked | Result |
| --- | --- |
| Customer share of revenue | C001–C010 all ≈10.0% |
| Product share of revenue | P001–P010 all ≈10.0% |
| Monthly revenue | CV 0.038 — no trend, no seasonality |
| `MRP` | ~1,978 distinct prices *per product* — not a price list |
| `Qty` / `Discount` | uniform 1–5 / uniform 0–0.10 |
| **`Target` vs actuals** | **correlation ≈ 0.00** (qty −0.019, revenue 0.008) |

`Target` is uniform random in [100, 1000] and unrelated to anything else in
the dataset, so achievement lands near 15% and every month shows red. That is
the data, not a finding. The app says so in a banner.

This is fine for what a POC needs to prove — 100K rows, real joins, real date
handling, the drill paths — but swap in real extracts before drawing any
conclusion. Point `DataPaths` at your own files; nothing downstream changes:

```python
from poc_bi import DataPaths, build_fact

paths = DataPaths(
    transactions=Path(r"C:\extracts\sales.csv"),
    targets=Path(r"C:\extracts\targets.csv"),
    customers=Path(r"C:\extracts\customers.csv"),
    products=Path(r"C:\extracts\products.csv"),
)
fact = build_fact(paths)
```

## Layout

```
app.py                    Streamlit dashboard (presentation only)
src/poc_bi/data.py        Loading + cleaning; every raw-CSV quirk handled here
src/poc_bi/metrics.py     Aggregations; no IO, no plotting
src/poc_bi/theme.py       Chart palette and Plotly chrome
scripts/setup.ps1         Windows environment setup (PowerShell)
scripts/setup.bat         Windows environment setup (cmd.exe fallback)
scripts/setup_claude_code.ps1     Install Claude Code + Remote Control preflight
scripts/start_remote_control.ps1  Start a phone-drivable session (holds PC awake)
scripts/verify_data.py    Data health check
scripts/export_clean.py   Clean data out to Excel/CSV for Power BI or Excel
tests/                    43 tests, mostly regression cover for the quirks
docs/windows-setup.md     Full Windows guide + data dictionary
docs/mobile-remote-control.md  Drive this machine from your phone
```

The layering matters: **business logic lives in `metrics.py`, not in the app.**
If the POC lands on Power BI or an Excel model instead of Streamlit, the data
and metrics layers carry over — `scripts/export_clean.py` already writes clean,
joined, ready-to-model output.

## The data quirks

All handled in `src/poc_bi/data.py`; listed in full in
[docs/windows-setup.md](docs/windows-setup.md#data-notes). The two that cause
silent wrong answers rather than errors:

- **`Date` is an Excel serial number** (45292–46386), not a date string.
  Convert with an 1899-12-30 origin → 2024-01-01 to 2026-12-30.
- **IDs are padded inconsistently.** Masters say `C010`/`P010`; transactions
  and targets say `C0010`/`P0010`. Joining without normalizing silently drops
  the 10th customer and the 10th product — no error, just wrong totals.

Plus: the transaction header's trailing comma creates an unnamed counter
column, and the final row is blank. Order matters when cleaning those two —
the blank row carries a value in the counter column, so it only *looks* blank
once that column is dropped. `tests/test_data.py` locks that ordering in.

## Development

```powershell
pytest                              # 43 tests
python scripts\verify_data.py       # data health check
python scripts\export_clean.py      # -> output\poc_bi_clean.xlsx
```

Requires Python 3.10+. Dependencies pinned in `requirements.txt`.
