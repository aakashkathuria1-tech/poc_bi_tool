# CLAUDE.md

Guidance for AI assistants working in this repository.

## 1. What this repository is

`poc_bi_tool` is a proof-of-concept for a sales BI / analytics tool. **As of the current commit it
contains no application code** — only four CSV files that form a small star schema of synthetic
sales data.

```
poc_bi_tool/
├── test_cust_master.csv      # dimension: 10 customers
├── test_product_master.csv   # dimension: 10 products
├── test_trans_data.csv       # fact: 100,338 transaction lines (~5.8 MB)
└── test_month_targets.csv    # fact: 2,100 monthly targets
```

Everything landed in a single commit (`85d0c21`, "Add files via upload"). There is no build system,
no dependency manifest, no test suite, no CI, and no README.

**Implication for you:** when asked to "add a feature" or "fix a bug", there is no existing code to
match. You are establishing the conventions, not following them. Read §7 before creating structure,
and prefer asking about stack choice over silently inventing one.

## 2. Data model

A textbook star schema. Two dimensions hang off the transaction fact; targets are a second fact
table at a coarser grain.

```
test_cust_master (customer_id)      test_product_master (product_id)
        │                                    │
        │  Cust_ID                  Prod_ID  │
        ├──────────► test_trans_data ◄───────┤     grain: one transaction line
        │                                    │
        └──────────► test_month_targets ◄────┘     grain: customer × product × month
```

### `test_cust_master.csv` — 10 rows

| Column | Type | Notes |
|---|---|---|
| `customer_id` | text | PK. `C001`–`C010` |
| `region` | text | `North`, `South`, `West`, `East` |
| `city` | text | Delhi, Noida, Gurgaon, Bangalore, Chennai, Hyderabad, Mumbai, Pune, Ahmedabad, Kolkata |
| `area_manager` | text | e.g. `AM_N1`; nested inside a zone |
| `zonal_manager` | text | e.g. `ZM_North`; 1:1 with `region` |

Hierarchy for roll-ups: `zonal_manager` → `area_manager` → `customer_id`, and `region` → `city`.

### `test_product_master.csv` — 10 rows

| Column | Type | Notes |
|---|---|---|
| `product_id` | text | PK. `P001`–`P010` |
| `category` | text | `Electronics`, `Home`, `Fashion`, `Auto` |
| `sub_category` | text | `Accessories` appears under **both** Electronics and Auto — always group by `(category, sub_category)`, never `sub_category` alone |

### `test_trans_data.csv` — 100,339 data rows (100,338 usable, see §3.5)

Header: `Cust_ID,Prod_ID,Date,Order No,Item No,Qty,MRP,Cost,Discount,` — note the **trailing comma**.
Every row has 10 fields; the 10th is unnamed.

| Column | Type | Range / notes |
|---|---|---|
| `Cust_ID` | text | FK → `customer_id`. **See §3.1** |
| `Prod_ID` | text | FK → `product_id`. **See §3.1** |
| `Date` | **Excel serial int** | 45292–46386 = 2024-01-01 … 2026-12-30. **See §3.2** |
| `Order No` | text | `O00` + decimal counter, so width varies: `O001`, `O0010`, `O00100`, … `O0099999` |
| `Item No` | text | Not a reliable key. **See §3.4** |
| `Qty` | int | 1–5, uniform |
| `MRP` | float | 10–2000. **Unit** list price, not line total |
| `Cost` | float | 2–600. **Unit** cost. Always 20–30% of `MRP`; never exceeds it |
| `Discount` | float | 0–0.10 in 0.01 steps. A **fraction**, not a percentage |
| *(unnamed 10th)* | int | Artifact of generation. **See §3.3** — do not treat as data |

### `test_month_targets.csv` — 2,100 rows

| Column | Type | Notes |
|---|---|---|
| `Cust_ID` | text | FK → customer. **See §3.1** |
| `Prod_ID` | text | FK → product |
| `Month` | text | `%d-%b-%y`, e.g. `01-Apr-24`. Always the 1st of the month |
| `Target` | int | 100–1000, uniform random |

Dense and complete: 10 customers × 10 products × 21 months (`01-Apr-24` … `01-Dec-25`) = 2,100 rows
exactly, with `(Cust_ID, Prod_ID, Month)` unique. No gaps to fill.

## 3. Data quirks — read before writing any join or parser

These are all verified properties of the committed files, not hypotheticals. Most of them fail
*silently*.

### 3.1 Customer/product IDs do not match between masters and facts

The masters use `C010` / `P010`. The fact tables use **`C0010` / `P0010`** — an extra zero. `C010`
and `P010` appear **nowhere** in `test_trans_data.csv`.

* 9,803 rows carry `C0010`; 9,986 carry `P0010`.
* A naive inner join against both masters silently drops **18,865 of 100,338 rows (18.8%)**.
* `test_month_targets.csv` is inconsistent with *itself*: it uses the broken `C0010` but the
  correct `P010`.

Normalize keys before joining. Do not "fix" the CSVs in place — normalize in the loader so the raw
files stay reproducible:

```python
def norm_id(s: str) -> str:
    # 'C0010' -> 'C010', 'C001' -> 'C001'
    prefix, digits = s[0], s[1:]
    return f"{prefix}{int(digits):03d}"
```

Always assert row counts before and after a join; a shrinking count means a key mismatch, not a
filter.

### 3.2 `Date` is an Excel serial number, not a date

Values like `46007` are day offsets in the Excel 1900 system. Convert with epoch **1899-12-30**:

```python
from datetime import date, timedelta
EXCEL_EPOCH = date(1899, 12, 30)
d = EXCEL_EPOCH + timedelta(days=int(serial))
```

`pd.read_csv` will type this column as `int64` and every date operation will fail or, worse,
succeed with nonsense. Convert at load time.

Coverage is 2024-01-01 → 2026-12-30, spread evenly (~33k rows per calendar year). Note this is
**wider than the target window** (Apr-2024 → Dec-2025): 41,496 rows (41%) fall outside it and have
no target to compare against. Decide explicitly whether to filter or to show them with a null
target.

### 3.3 The unnamed 10th column is a generation artifact

The file was produced in two passes, and the 10th column means something different in each:

* **Rows 1–99,999** — one row per order, `Item No` = `<Order No>-1`, 10th column = a sequential row
  counter `1…99999`.
* **Rows 100,000–100,339** (340 rows) — extra line items appended to 333 orders that already exist
  in the first block. `Item No` = `<Order No>` + item index with **no dash**, and the 10th column is
  the item index (2–5).

Drop this column on load. Do not sum it, group by it, or use it as an ID.

### 3.4 `Order No` is not a valid grain key, and `Item No` is not unique

Of the 333 multi-line orders, **301 have a different `Cust_ID` across their lines and all 333 have a
different `Date`**. The appended block was generated without reference to the parent order, so a
single `Order No` can span two customers and two dates.

Consequences:

* Never attribute a customer, date, or region at the `Order No` level. Attribute per row.
* "Orders per customer" via `nunique(Order No)` will double-count. If you need an order count, it is
  only meaningful on the first 99,999 rows.
* `Item No` has 4 genuine duplicate values (e.g. `O0071862` appears twice, same order and same item
  index). It is **not** a primary key. There is no natural PK — use the row index.

There are no fully duplicated rows across all 9 named columns.

### 3.5 One fully blank row

The final line of `test_trans_data.csv` is `,,,,,,,,,5` — every named field empty, 10th column `5`.
Drop rows with a blank `Cust_ID` at load. It is the only such row, and it will otherwise turn into
`NaN` totals or a phantom "" customer in every group-by.

### 3.6 Targets do not reconcile with transactions

`Target` is uniform random in 100–1000 and was generated independently of the transaction data. Over
the overlapping window the totals are ~1.19M target units vs ~176.6K actual units and ~₹168M actual
revenue — matching neither on units nor on value.

Achievement percentages will look absurd (single-digit percentages, wild swings). **That is a
property of the synthetic data, not a bug in the aggregation.** Do not "correct" it, and do not
spend time debugging a variance calculation that is arithmetically right. If a demo needs plausible
numbers, scale targets explicitly and say so in the code.

### 3.7 File format details

* **CRLF (`\r\n`) line endings** on all four files. `csv` and `pandas` handle this; hand-rolled
  `split('\n')` parsing will leave a trailing `\r` on the last field of every row.
* ASCII, no BOM. Reading with `encoding='utf-8-sig'` is harmless and future-proofs against one.
* `test_trans_data.csv` is ~5.8 MB / 100k rows — small enough to load whole. No chunking needed.

## 4. Derived metric conventions

Nothing in the repo defines these. `MRP` and `Cost` are both **per unit** (confirmed: `Cost` is a
flat 20–30% of `MRP` on every row and never exceeds it), and `Discount` is a fraction. Adopt these
definitions and keep them in one shared module so they don't drift:

```python
gross    = Qty * MRP                  # pre-discount line value
revenue  = Qty * MRP * (1 - Discount) # net of discount
cogs     = Qty * Cost
margin   = revenue - cogs
margin_pct = margin / revenue         # guard against revenue == 0
```

Targets are expressed in the same grain as `Qty` sums (see §3.6 for the caveat):

```python
achievement_pct = actual / target     # join on (customer, product, month-start)
```

If the business intends `Target` to be revenue rather than units, that changes every variance
number — worth confirming with the user before building reporting on top of it.

## 5. Business context

The data models an Indian distribution business, which shapes the expected reporting:

* **Fiscal year runs April–March.** Targets start at `01-Apr-24`, confirming FY convention. Report
  periods should default to FY, not calendar year. By FY the rows split 8,240 (FY23, partial) /
  33,401 (FY24) / 33,808 (FY25) / 24,889 (FY26, partial).
* **Sales hierarchy** is Zonal Manager → Area Manager → Customer, parallel to Region → City. Both
  drill-down paths are expected in a BI tool.
* Currency is INR; `MRP` (Maximum Retail Price) is standard Indian retail terminology.

## 6. Working with this repository

### Git conventions

* Default branch is `main`.
* Work on the branch you were assigned; do not push to `main` directly.
* Push with `git push -u origin <branch>` and open a **draft** PR.
* There is no PR template, no linter config, and no CI. Nothing gates a merge, so review carefully.

### Verifying data claims

There is no test suite to catch a bad assumption. `pandas` is **not installed** in the default
environment (Python 3.11); either `pip install pandas` or use the stdlib `csv` module for quick
checks. Re-derive counts from the files rather than trusting numbers quoted in this document if a
decision depends on them.

### Do not

* **Do not edit or regenerate the CSVs.** They are the fixture the POC is built against. Fix data
  problems in loader code so the raw inputs stay reproducible and reviewable.
* Do not commit large derived artifacts (parquet caches, exports, `.db` files) — add a `.gitignore`
  first.
* Do not treat this synthetic data as realistic when reasoning about performance. Ten customers and
  ten products will make any approach look fast; real cardinality will not.

## 7. If you are adding the first application code

The repo has no stack committed yet. Ask the user before choosing one — Python/pandas + Streamlit,
a notebook, DuckDB, and a JS dashboard are all consistent with what's here, and the choice is not
recoverable cheaply. Once chosen:

1. **Put loading and cleaning in one module.** Every quirk in §3 must be handled exactly once, at
   load time — key normalization, Excel-serial dates, dropping the unnamed column and the blank row.
   Bugs here are silent and contaminate every downstream number.
2. **Add a dependency manifest** (`requirements.txt` / `pyproject.toml` / `package.json`) in the same
   commit as the first import.
3. **Add tests for the loader first.** Assert the post-load row count is 100,338, that all keys join
   without loss, and that dates land in 2024–2026. These are the assertions that catch the §3
   traps regressing.
4. **Update this file** with the real structure, the run command, and the test command.
