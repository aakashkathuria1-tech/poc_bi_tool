"""Aggregations the dashboard reads.

Everything here takes an already-clean fact table from data.py and returns a
frame ready to chart or table. No file IO, no plotting - so these are cheap to
test and reusable from a notebook, an Excel export, or a different front end.
"""

from __future__ import annotations

import pandas as pd

# Measures that are safe to sum. Anything derived from a ratio (margin %,
# achievement %) has to be recomputed after aggregation, never averaged -
# averaging a ratio of ratios is the classic silent BI bug.
ADDITIVE_MEASURES = [
    "Qty",
    "gross_revenue",
    "net_revenue",
    "discount_value",
    "cogs",
    "gross_profit",
]

# Dimension label -> column, for the dashboard's "break down by" control.
DIMENSIONS: dict[str, str] = {
    "Region": "region",
    "City": "city",
    "Zonal manager": "zonal_manager",
    "Area manager": "area_manager",
    "Category": "category",
    "Sub-category": "sub_category",
    "Customer": "Cust_ID",
    "Product": "Prod_ID",
}


def filter_fact(
    fact: pd.DataFrame,
    date_from: pd.Timestamp | None = None,
    date_to: pd.Timestamp | None = None,
    regions: list[str] | None = None,
    categories: list[str] | None = None,
    zonal_managers: list[str] | None = None,
) -> pd.DataFrame:
    """Apply the dashboard's filters. Empty/None means 'no filter'."""
    mask = pd.Series(True, index=fact.index)
    if date_from is not None:
        mask &= fact["Date"] >= pd.Timestamp(date_from)
    if date_to is not None:
        mask &= fact["Date"] <= pd.Timestamp(date_to)
    if regions:
        mask &= fact["region"].isin(regions)
    if categories:
        mask &= fact["category"].isin(categories)
    if zonal_managers:
        mask &= fact["zonal_manager"].isin(zonal_managers)
    return fact[mask]


def headline_kpis(fact: pd.DataFrame) -> dict[str, float]:
    """The numbers the KPI row leads with."""
    net = float(fact["net_revenue"].sum())
    gross = float(fact["gross_revenue"].sum())
    profit = float(fact["gross_profit"].sum())
    return {
        "net_revenue": net,
        "gross_revenue": gross,
        "units": float(fact["Qty"].sum()),
        "orders": float(fact["Order No"].nunique()),
        "gross_profit": profit,
        # Recomputed from the summed components, not averaged per row.
        "margin_pct": (profit / net * 100) if net else 0.0,
        "discount_pct": ((gross - net) / gross * 100) if gross else 0.0,
        "avg_order_value": (net / fact["Order No"].nunique())
        if fact["Order No"].nunique()
        else 0.0,
    }


def monthly_trend(fact: pd.DataFrame) -> pd.DataFrame:
    """Net revenue, units and margin by month."""
    out = (
        fact.groupby("Month", as_index=False)[ADDITIVE_MEASURES]
        .sum()
        .sort_values("Month")
    )
    out["margin_pct"] = (out["gross_profit"] / out["net_revenue"] * 100).fillna(0)
    return out


def breakdown(
    fact: pd.DataFrame, dimension: str, measure: str = "net_revenue", top_n: int | None = None
) -> pd.DataFrame:
    """Aggregate one measure by one dimension, largest first.

    Passing top_n folds the tail into a single 'Other' row rather than
    dropping it, so the total still reconciles to the KPI row.
    """
    if dimension not in fact.columns:
        raise KeyError(f"{dimension!r} is not a column on the fact table")

    out = (
        fact.groupby(dimension, as_index=False, dropna=False)[ADDITIVE_MEASURES]
        .sum()
        .sort_values(measure, ascending=False)
        .reset_index(drop=True)
    )
    out["margin_pct"] = (out["gross_profit"] / out["net_revenue"] * 100).fillna(0)

    if top_n is not None and len(out) > top_n:
        head = out.head(top_n).copy()
        tail = out.tail(len(out) - top_n)
        other = {c: tail[c].sum() for c in ADDITIVE_MEASURES}
        other[dimension] = "Other"
        other["margin_pct"] = (
            other["gross_profit"] / other["net_revenue"] * 100
            if other["net_revenue"]
            else 0.0
        )
        out = pd.concat([head, pd.DataFrame([other])], ignore_index=True)

    total = out[measure].sum()
    out["share_pct"] = (out[measure] / total * 100) if total else 0.0
    return out


def actual_vs_target(
    fact: pd.DataFrame,
    targets: pd.DataFrame,
    dimension: str | None = None,
    measure: str = "Qty",
) -> pd.DataFrame:
    """Compare actuals against targets on the overlapping months only.

    Targets cover a narrower window than the transactions, so an unrestricted
    comparison would score real months against a target of zero and show a
    cliff that is not there. Both sides are clipped to the intersection of the
    two month ranges, and the window is returned on the frame's `attrs` so the
    caller can state it.

    NOTE ON THE SAMPLE DATA: the shipped Target column is uniform random noise
    (it correlates with actuals at ~0.00), so these numbers exercise the
    calculation but carry no business meaning. See README.
    """
    if targets.empty or fact.empty:
        return pd.DataFrame()

    window = sorted(set(fact["Month"]) & set(targets["Month"]))
    if not window:
        return pd.DataFrame()

    fact_w = fact[fact["Month"].isin(window)]
    targets_w = targets[targets["Month"].isin(window)]

    group = ["Month"] if dimension is None else [dimension]
    actual = fact_w.groupby(group, as_index=False, dropna=False)[measure].sum()
    actual = actual.rename(columns={measure: "actual"})
    target = targets_w.groupby(group, as_index=False, dropna=False)["Target"].sum()
    target = target.rename(columns={"Target": "target"})

    out = actual.merge(target, on=group, how="outer").fillna({"actual": 0, "target": 0})
    out["variance"] = out["actual"] - out["target"]
    out["achievement_pct"] = (
        (out["actual"] / out["target"] * 100).where(out["target"] != 0)
    ).fillna(0)
    out = out.sort_values(group[0]).reset_index(drop=True)

    out.attrs["window_start"] = min(window)
    out.attrs["window_end"] = max(window)
    out.attrs["measure"] = measure
    return out


def coverage_note(fact: pd.DataFrame, targets: pd.DataFrame) -> str:
    """One line stating how much of the data the target comparison covers."""
    if fact.empty or targets.empty:
        return "No overlapping period between transactions and targets."
    window = set(fact["Month"]) & set(targets["Month"])
    if not window:
        return "No overlapping period between transactions and targets."
    covered = fact["Month"].isin(window).sum()
    start, end = min(window), max(window)
    return (
        f"Target comparison covers {start:%b %Y} - {end:%b %Y}: "
        f"{covered:,} of {len(fact):,} transactions ({covered / len(fact):.0%})."
    )
