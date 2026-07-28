"""Health-check the poc_bi_tool data.

Two jobs:

1. Prove the local environment works - if this runs clean, Python, the venv
   and the dependencies are all wired up correctly.
2. Report on the data after cleaning, so problems surface here rather than in
   a dashboard number nobody can explain.

The cleaning itself lives in poc_bi.data, not here - one implementation, so
this check and the dashboard can never disagree about what the data says.

Usage (from the repo root, with the venv active):

    python scripts\\verify_data.py

Exits 0 if the data looks usable, 1 if a hard error was found.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    import pandas as pd
except ImportError:
    sys.exit(
        "pandas is not installed.\n"
        "Activate the venv first (.venv\\Scripts\\Activate.ps1), or run "
        "scripts\\setup.ps1 to create it."
    )

from poc_bi import data, metrics  # noqa: E402

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


def check_transactions(paths: data.DataPaths) -> pd.DataFrame:
    print("\ntest_trans_data.csv")
    raw = pd.read_csv(paths.transactions)
    df = data.load_transactions(paths)

    dropped = len(raw) - len(df)
    if dropped:
        warn(f"dropped {dropped} blank row(s) during load")

    if df["Date"].isna().any():
        fail(f"{int(df['Date'].isna().sum())} row(s) have an unparseable Date")
    else:
        ok(
            f"{len(df):,} rows, dates {df['Date'].min():%Y-%m-%d} "
            f"to {df['Date'].max():%Y-%m-%d} (converted from Excel serials)"
        )

    for col in ("Qty", "MRP", "Cost", "Discount"):
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
    return df


def check_targets(paths: data.DataPaths) -> pd.DataFrame:
    print("\ntest_month_targets.csv")
    df = data.load_targets(paths)

    if df["Month"].isna().any():
        fail(f"{int(df['Month'].isna().sum())} row(s) have an unparseable Month")
    else:
        ok(f"{len(df):,} rows, {df['Month'].min():%b %Y} to {df['Month'].max():%b %Y}")

    if df["Target"].isna().any():
        fail(f"{int(df['Target'].isna().sum())} row(s) have a non-numeric Target")

    if df.duplicated(subset=["Cust_ID", "Prod_ID", "Month"]).any():
        fail("duplicate (Cust_ID, Prod_ID, Month) rows - grain is not unique")
    else:
        ok("one target per customer / product / month")
    return df


def check_masters(paths: data.DataPaths) -> None:
    print("\nmaster files")
    cust = data.load_customers(paths)
    prod = data.load_products(paths)

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


def check_joins(fact: pd.DataFrame) -> None:
    print("\nreferential integrity (after ID normalization)")
    for col, label in (("region", "customer"), ("category", "product")):
        orphans = fact[fact[col].isna()]
        if not orphans.empty:
            key = "Cust_ID" if label == "customer" else "Prod_ID"
            fail(
                f"{len(orphans)} row(s) have a {label} ID not in the master: "
                f"{sorted(orphans[key].dropna().unique())[:5]}"
            )
        else:
            ok(f"every {label} ID resolves to the master")

    if fact["Cust_ID"].nunique() != 10 or fact["Prod_ID"].nunique() != 10:
        warn(
            f"expected 10 customers and 10 products, saw "
            f"{fact['Cust_ID'].nunique()} and {fact['Prod_ID'].nunique()}"
        )


def summarize(fact: pd.DataFrame, targets: pd.DataFrame) -> None:
    print("\nsample rollup")
    k = metrics.headline_kpis(fact)
    print(f"  gross revenue {k['gross_revenue']:>16,.0f}")
    print(f"  net revenue   {k['net_revenue']:>16,.0f}")
    print(f"  gross profit  {k['gross_profit']:>16,.0f}  ({k['margin_pct']:.1f}% margin)")
    print(f"  units         {k['units']:>16,.0f}")
    print(f"  orders        {k['orders']:>16,.0f}")
    print(f"\n  {metrics.coverage_note(fact, targets)}")


def main() -> int:
    paths = data.DataPaths.samples()
    if missing := paths.missing():
        sys.exit(
            "Missing data file(s):\n  "
            + "\n  ".join(str(p) for p in missing)
            + "\n\nRun this from the repo root."
        )

    print("=" * 66)
    print("poc_bi_tool - data health check")
    print(f"repo: {data.REPO_ROOT}")
    print(f"pandas {pd.__version__} on Python {sys.version.split()[0]}")
    print("=" * 66)

    check_transactions(paths)
    targets = check_targets(paths)
    check_masters(paths)

    fact = data.build_fact(paths)
    check_joins(fact)
    summarize(fact, targets)

    print("\n" + "=" * 66)
    if errors:
        print(f"FAILED - {len(errors)} error(s), {len(warnings)} warning(s)")
        for msg in errors:
            print(f"  - {msg}")
        return 1
    print(f"PASSED - environment and data are usable ({len(warnings)} warning(s))")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
