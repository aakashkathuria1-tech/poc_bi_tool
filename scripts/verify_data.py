"""Health-check the poc_bi_tool sample data.

Two jobs:

1. Prove the local environment works - if this runs clean, Python, the venv
   and pandas are all wired up correctly.
2. Report on the raw CSVs, including the known quirks that any code reading
   this data has to deal with (Excel serial dates, zero-padding mismatch
   between the transaction IDs and the master IDs, one all-blank row).

Usage (from the repo root, with the venv active):

    python scripts\\verify_data.py

Exits 0 if the data looks usable, 1 if a hard error was found.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit(
        "pandas is not installed.\n"
        "Activate the venv first (.venv\\Scripts\\Activate.ps1), or run "
        "scripts\\setup.ps1 to create it."
    )

REPO_ROOT = Path(__file__).resolve().parent.parent

TRANSACTIONS = REPO_ROOT / "test_trans_data.csv"
TARGETS = REPO_ROOT / "test_month_targets.csv"
CUSTOMERS = REPO_ROOT / "test_cust_master.csv"
PRODUCTS = REPO_ROOT / "test_product_master.csv"

# Excel on Windows counts days from this date (it treats 1900 as a leap year,
# so the usable epoch is the 30th, not the 31st).
EXCEL_EPOCH = "1899-12-30"

errors: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"  [FAIL] {msg}")


def normalize_id(series: pd.Series) -> pd.Series:
    """Collapse C001 / C0010 style IDs onto one zero-padded form.

    The masters use C001..C010, the transaction and target files use
    C001..C009 plus C0010. Splitting off the letter prefix and re-padding the
    number makes both sides join.
    """
    prefix = series.str.slice(0, 1)
    number = pd.to_numeric(series.str.slice(1), errors="coerce")
    return prefix + number.map(lambda n: "" if pd.isna(n) else f"{int(n):03d}")


def require(path: Path) -> None:
    if not path.exists():
        sys.exit(
            f"Missing data file: {path}\n"
            "Run this from the repo root, and check the CSVs were cloned "
            "(they are large - confirm Git LFS is not required)."
        )


def load_transactions() -> pd.DataFrame:
    print("\ntest_trans_data.csv")
    df = pd.read_csv(TRANSACTIONS, dtype={"Cust_ID": str, "Prod_ID": str})

    # The header has a trailing comma, so pandas invents an unnamed final
    # column. It is just a row counter - drop it.
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed:")]
    if unnamed:
        df = df.drop(columns=unnamed)
        ok(f"dropped trailing unnamed column ({', '.join(unnamed)})")

    raw_rows = len(df)
    df = df.dropna(how="all")
    if len(df) < raw_rows:
        warn(f"dropped {raw_rows - len(df)} all-blank row(s)")

    df["Date"] = pd.to_datetime(
        pd.to_numeric(df["Date"], errors="coerce"), unit="D", origin=EXCEL_EPOCH
    )
    if df["Date"].isna().any():
        fail(f"{int(df['Date'].isna().sum())} row(s) have an unparseable Date")
    else:
        ok(
            f"{len(df):,} rows, dates {df['Date'].min():%Y-%m-%d} "
            f"to {df['Date'].max():%Y-%m-%d} (converted from Excel serials)"
        )

    for col in ("Qty", "MRP", "Cost", "Discount"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            fail(f"{col} has {int(df[col].isna().sum())} non-numeric value(s)")

    if (df["Qty"] <= 0).any():
        warn(f"{int((df['Qty'] <= 0).sum())} row(s) have Qty <= 0")
    if not df["Discount"].between(0, 1).all():
        warn("Discount has values outside 0..1 - confirm it is a fraction")

    dupes = int(df.duplicated(subset=["Order No", "Item No"]).sum())
    if dupes:
        warn(f"{dupes} duplicate (Order No, Item No) pair(s)")
    else:
        ok("(Order No, Item No) is unique")

    df["Cust_ID"] = normalize_id(df["Cust_ID"])
    df["Prod_ID"] = normalize_id(df["Prod_ID"])
    return df


def load_targets() -> pd.DataFrame:
    print("\ntest_month_targets.csv")
    df = pd.read_csv(TARGETS, dtype={"Cust_ID": str, "Prod_ID": str})
    df = df.dropna(how="all")

    df["Month"] = pd.to_datetime(df["Month"], format="%d-%b-%y", errors="coerce")
    if df["Month"].isna().any():
        fail(f"{int(df['Month'].isna().sum())} row(s) have an unparseable Month")
    else:
        ok(
            f"{len(df):,} rows, {df['Month'].min():%b %Y} "
            f"to {df['Month'].max():%b %Y}"
        )

    df["Target"] = pd.to_numeric(df["Target"], errors="coerce")
    if df["Target"].isna().any():
        fail(f"{int(df['Target'].isna().sum())} row(s) have a non-numeric Target")

    df["Cust_ID"] = normalize_id(df["Cust_ID"])
    df["Prod_ID"] = normalize_id(df["Prod_ID"])

    grain = int(df.duplicated(subset=["Cust_ID", "Prod_ID", "Month"]).sum())
    if grain:
        fail(f"{grain} duplicate (Cust_ID, Prod_ID, Month) row(s) - grain is not unique")
    else:
        ok("one target per customer / product / month")
    return df


def load_masters() -> tuple[pd.DataFrame, pd.DataFrame]:
    print("\nmaster files")
    cust = pd.read_csv(CUSTOMERS, dtype={"customer_id": str})
    prod = pd.read_csv(PRODUCTS, dtype={"product_id": str})
    cust["customer_id"] = normalize_id(cust["customer_id"])
    prod["product_id"] = normalize_id(prod["product_id"])

    if cust["customer_id"].duplicated().any():
        fail("duplicate customer_id in test_cust_master.csv")
    if prod["product_id"].duplicated().any():
        fail("duplicate product_id in test_product_master.csv")

    ok(
        f"{len(cust)} customers across {cust['region'].nunique()} regions, "
        f"{cust['zonal_manager'].nunique()} zonal / "
        f"{cust['area_manager'].nunique()} area managers"
    )
    ok(f"{len(prod)} products across {prod['category'].nunique()} categories")
    return cust, prod


def check_joins(
    trans: pd.DataFrame,
    targets: pd.DataFrame,
    cust: pd.DataFrame,
    prod: pd.DataFrame,
) -> None:
    print("\nreferential integrity (after ID normalization)")
    known_cust = set(cust["customer_id"])
    known_prod = set(prod["product_id"])

    for name, df, cust_col, prod_col in (
        ("transactions", trans, "Cust_ID", "Prod_ID"),
        ("targets", targets, "Cust_ID", "Prod_ID"),
    ):
        orphan_c = set(df[cust_col]) - known_cust
        orphan_p = set(df[prod_col]) - known_prod
        if orphan_c:
            fail(f"{name}: customer IDs not in the master: {sorted(orphan_c)}")
        else:
            ok(f"{name}: every customer ID resolves to the master")
        if orphan_p:
            fail(f"{name}: product IDs not in the master: {sorted(orphan_p)}")
        else:
            ok(f"{name}: every product ID resolves to the master")


def summarize(trans: pd.DataFrame, targets: pd.DataFrame) -> None:
    """A first cut at the numbers a BI layer would sit on top of."""
    print("\nsample rollup (gross = Qty * MRP, net = gross less Discount)")
    trans = trans.assign(
        gross=trans["Qty"] * trans["MRP"],
        net=trans["Qty"] * trans["MRP"] * (1 - trans["Discount"]),
    )
    print(f"  gross  {trans['gross'].sum():>16,.0f}")
    print(f"  net    {trans['net'].sum():>16,.0f}")
    print(f"  units  {trans['Qty'].sum():>16,.0f}")
    # The Target column carries no unit of measure - it is ~4x total Qty, so
    # it is probably not units. Confirm with the data owner before comparing.
    print(f"  target {targets['Target'].sum():>16,.0f} (Target column, Apr 24 - Dec 25)")

    overlap = trans[trans["Date"].dt.to_period("M").isin(
        targets["Month"].dt.to_period("M")
    )]
    print(
        f"\n  {len(overlap):,} of {len(trans):,} transactions "
        f"({len(overlap) / len(trans):.0%}) fall inside the target window"
    )


def main() -> int:
    for path in (TRANSACTIONS, TARGETS, CUSTOMERS, PRODUCTS):
        require(path)

    print("=" * 62)
    print("poc_bi_tool - data health check")
    print(f"repo: {REPO_ROOT}")
    print(f"pandas {pd.__version__} on Python {sys.version.split()[0]}")
    print("=" * 62)

    trans = load_transactions()
    targets = load_targets()
    cust, prod = load_masters()
    check_joins(trans, targets, cust, prod)
    summarize(trans, targets)

    print("\n" + "=" * 62)
    if errors:
        print(f"FAILED - {len(errors)} error(s), {len(warnings)} warning(s)")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print(f"PASSED - environment and data are usable ({len(warnings)} warning(s))")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
