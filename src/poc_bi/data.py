"""Loading and cleaning layer.

Every quirk in the raw CSVs is handled here and nowhere else, so the rest of
the codebase can assume clean, joined data. See docs/windows-setup.md for the
full list; the short version:

  - Date is an Excel serial number, not a date
  - IDs are padded inconsistently (masters C010 vs facts C0010)
  - The transaction header's trailing comma yields an unnamed counter column
  - The last transaction row is blank

To point this at real extracts instead of the samples, build a DataPaths with
your own file locations - nothing downstream needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

# Excel on Windows counts days from this date (it treats 1900 as a leap year,
# so the usable epoch is the 30th, not the 31st).
EXCEL_EPOCH = "1899-12-30"


@dataclass(frozen=True)
class DataPaths:
    """Where the four source files live."""

    transactions: Path
    targets: Path
    customers: Path
    products: Path

    @classmethod
    def samples(cls, root: Path | None = None) -> "DataPaths":
        root = Path(root) if root is not None else REPO_ROOT
        return cls(
            transactions=root / "test_trans_data.csv",
            targets=root / "test_month_targets.csv",
            customers=root / "test_cust_master.csv",
            products=root / "test_product_master.csv",
        )

    def missing(self) -> list[Path]:
        return [
            p
            for p in (self.transactions, self.targets, self.customers, self.products)
            if not p.exists()
        ]


def normalize_id(series: pd.Series) -> pd.Series:
    """Collapse C001 / C0010 style IDs onto one zero-padded form.

    The masters use C001..C010; the transaction and target files use
    C001..C009 plus C0010. Without this, a join silently drops the 10th
    customer and the 10th product - no error, just quietly wrong totals.
    """
    text = series.astype("string").str.strip()
    prefix = text.str.slice(0, 1)
    number = pd.to_numeric(text.str.slice(1), errors="coerce")
    padded = number.map(lambda n: pd.NA if pd.isna(n) else f"{int(n):03d}")
    return (prefix + padded.astype("string")).astype("object")


def _drop_counter_column(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the unnamed row-counter pandas invents from the trailing comma."""
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed:")]
    return df.drop(columns=unnamed) if unnamed else df


def load_transactions(paths: DataPaths | None = None) -> pd.DataFrame:
    """Order lines, one row each, with a real Date and normalized IDs."""
    paths = paths or DataPaths.samples()
    df = pd.read_csv(paths.transactions, dtype={"Cust_ID": str, "Prod_ID": str})

    # Order matters: the blank final row carries a value in the counter
    # column, so it only looks blank once that column is gone. Dropping rows
    # first would leave it in the frame.
    df = _drop_counter_column(df).dropna(how="all")

    df["Date"] = pd.to_datetime(
        pd.to_numeric(df["Date"], errors="coerce"), unit="D", origin=EXCEL_EPOCH
    )
    for col in ("Qty", "MRP", "Cost", "Discount"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Cust_ID"] = normalize_id(df["Cust_ID"])
    df["Prod_ID"] = normalize_id(df["Prod_ID"])
    df["Month"] = df["Date"].values.astype("datetime64[M]")
    return df.reset_index(drop=True)


def load_targets(paths: DataPaths | None = None) -> pd.DataFrame:
    """Monthly targets at customer x product grain."""
    paths = paths or DataPaths.samples()
    df = pd.read_csv(paths.targets, dtype={"Cust_ID": str, "Prod_ID": str})
    df = df.dropna(how="all")

    df["Month"] = pd.to_datetime(df["Month"], format="%d-%b-%y")
    df["Target"] = pd.to_numeric(df["Target"], errors="coerce")
    df["Cust_ID"] = normalize_id(df["Cust_ID"])
    df["Prod_ID"] = normalize_id(df["Prod_ID"])
    return df.reset_index(drop=True)


def load_customers(paths: DataPaths | None = None) -> pd.DataFrame:
    paths = paths or DataPaths.samples()
    df = pd.read_csv(paths.customers, dtype={"customer_id": str}).dropna(how="all")
    df["customer_id"] = normalize_id(df["customer_id"])
    return df.reset_index(drop=True)


def load_products(paths: DataPaths | None = None) -> pd.DataFrame:
    paths = paths or DataPaths.samples()
    df = pd.read_csv(paths.products, dtype={"product_id": str}).dropna(how="all")
    df["product_id"] = normalize_id(df["product_id"])
    return df.reset_index(drop=True)


def build_fact(paths: DataPaths | None = None) -> pd.DataFrame:
    """The single enriched fact table everything else reads.

    One row per order line, with customer and product attributes joined on and
    the money measures derived. Left joins, so an ID missing from a master
    surfaces as a null attribute rather than a silently dropped row.
    """
    paths = paths or DataPaths.samples()
    fact = load_transactions(paths)
    customers = load_customers(paths)
    products = load_products(paths)

    fact = fact.merge(
        customers, how="left", left_on="Cust_ID", right_on="customer_id"
    ).merge(products, how="left", left_on="Prod_ID", right_on="product_id")
    fact = fact.drop(columns=["customer_id", "product_id"])

    return add_measures(fact)


def add_measures(fact: pd.DataFrame) -> pd.DataFrame:
    """Derive the money columns.

    MRP and Cost are per unit; Discount is a fraction of gross, not a
    percentage. Confirm those readings against the source system before
    anyone quotes the margin numbers.
    """
    fact = fact.copy()
    fact["gross_revenue"] = fact["Qty"] * fact["MRP"]
    fact["net_revenue"] = fact["gross_revenue"] * (1 - fact["Discount"])
    fact["discount_value"] = fact["gross_revenue"] - fact["net_revenue"]
    fact["cogs"] = fact["Qty"] * fact["Cost"]
    fact["gross_profit"] = fact["net_revenue"] - fact["cogs"]
    return fact


def build_target_fact(paths: DataPaths | None = None) -> pd.DataFrame:
    """Targets with customer and product attributes joined on."""
    paths = paths or DataPaths.samples()
    targets = load_targets(paths)
    customers = load_customers(paths)
    products = load_products(paths)

    targets = targets.merge(
        customers, how="left", left_on="Cust_ID", right_on="customer_id"
    ).merge(products, how="left", left_on="Prod_ID", right_on="product_id")
    return targets.drop(columns=["customer_id", "product_id"])
