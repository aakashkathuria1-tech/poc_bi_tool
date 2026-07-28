"""Sales performance dashboard.

Run it from the repo root with the venv active:

    streamlit run app.py

The app is a thin presentation layer - loading lives in poc_bi.data and every
calculation lives in poc_bi.metrics, so the same numbers can be driven from a
notebook or exported to Excel without going through Streamlit.
"""

from __future__ import annotations

import sys
from pathlib import Path

# src/ layout without requiring an install step.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from poc_bi import data, metrics, theme  # noqa: E402

st.set_page_config(page_title="Sales performance", layout="wide")


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading data...")
def get_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    paths = data.DataPaths.samples()
    missing = paths.missing()
    if missing:
        st.error(
            "Missing data file(s): "
            + ", ".join(p.name for p in missing)
            + "\n\nRun the app from the repo root."
        )
        st.stop()
    return data.build_fact(paths), data.build_target_fact(paths)


fact_all, targets_all = get_data()


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def money(value: float) -> str:
    """Compact currency for tiles; full precision belongs in the table view."""
    for cutoff, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= cutoff:
            return f"{value / cutoff:,.1f}{suffix}"
    return f"{value:,.0f}"


def count(value: float) -> str:
    return f"{value:,.0f}"


# --------------------------------------------------------------------------
# Filters - one row above the charts
# --------------------------------------------------------------------------
st.title("Sales performance")

st.warning(
    "**Sample data is synthetic and carries no signal.** Every customer and "
    "product holds a ~10% share, monthly revenue is flat (CV 0.04), and the "
    "Target column is uniform random noise that correlates with actuals at "
    "~0.00. The charts below are correct; the *patterns* in them are not "
    "findings. Point `DataPaths` at real extracts before drawing conclusions.",
    icon=":material/warning:",
)

min_date = fact_all["Date"].min().date()
max_date = fact_all["Date"].max().date()

f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
with f1:
    date_range = st.date_input(
        "Period",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
with f2:
    regions = st.multiselect("Region", sorted(fact_all["region"].dropna().unique()))
with f3:
    categories = st.multiselect(
        "Category", sorted(fact_all["category"].dropna().unique())
    )
with f4:
    managers = st.multiselect(
        "Zonal manager", sorted(fact_all["zonal_manager"].dropna().unique())
    )

date_from, date_to = (date_range if len(date_range) == 2 else (min_date, max_date))

fact = metrics.filter_fact(
    fact_all,
    date_from=pd.Timestamp(date_from),
    date_to=pd.Timestamp(date_to),
    regions=regions,
    categories=categories,
    zonal_managers=managers,
)

if fact.empty:
    st.info("No transactions match these filters.")
    st.stop()

# Keep targets on the same slice, so the comparison comes from like for like.
targets = targets_all.copy()
if regions:
    targets = targets[targets["region"].isin(regions)]
if categories:
    targets = targets[targets["category"].isin(categories)]
if managers:
    targets = targets[targets["zonal_manager"].isin(managers)]


# --------------------------------------------------------------------------
# KPI row - headline numbers are tiles, not a chart
# --------------------------------------------------------------------------
kpis = metrics.headline_kpis(fact)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Net revenue", money(kpis["net_revenue"]))
k2.metric("Units", count(kpis["units"]))
k3.metric("Orders", count(kpis["orders"]))
k4.metric("Gross margin", f"{kpis['margin_pct']:.1f}%")
k5.metric("Avg order value", money(kpis["avg_order_value"]))

st.caption(
    f"{len(fact):,} order lines - "
    f"{fact['Date'].min():%d %b %Y} to {fact['Date'].max():%d %b %Y} - "
    f"discount {kpis['discount_pct']:.1f}% of gross"
)

st.divider()


# --------------------------------------------------------------------------
# Trend - one series, so no legend; the title names it
# --------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Net revenue by month")
    trend = metrics.monthly_trend(fact)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend["Month"],
            y=trend["net_revenue"],
            mode="lines",
            line=dict(color=theme.CATEGORICAL_LIGHT[0], width=2),
            hovertemplate="%{x|%b %Y}<br>Net revenue %{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(hovermode="x unified")
    theme.apply_layout(fig, height=300)
    # Anchor at zero. A truncated axis turns this dataset's random +-4% jitter
    # into what looks like violent swings - the chart would contradict the
    # banner above it. Real seasonality still reads fine from a zero baseline.
    fig.update_yaxes(rangemode="tozero")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Break down by")
    dim_label = st.selectbox(
        "Dimension", list(metrics.DIMENSIONS), index=0, label_visibility="collapsed"
    )
    dim = metrics.DIMENSIONS[dim_label]

    # Magnitude comparison, so: one hue, more-is-darker, ranked.
    bd = metrics.breakdown(fact, dim, top_n=8).sort_values("net_revenue")
    shades = theme.sequential_shades(len(bd))[::-1]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=bd["net_revenue"],
            y=bd[dim].astype(str),
            orientation="h",
            marker=dict(color=shades, line=dict(color=theme.SURFACE, width=2)),
            hovertemplate="%{y}<br>Net revenue %{x:,.0f}<extra></extra>",
        )
    )
    theme.apply_layout(fig, height=300)
    fig.update_xaxes(showgrid=True, gridcolor=theme.GRIDLINE, griddash="dot")
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, use_container_width=True)

with st.expander(f"Table - by {dim_label.lower()}"):
    table = metrics.breakdown(fact, dim)
    st.dataframe(
        table[[dim, "Qty", "net_revenue", "gross_profit", "margin_pct", "share_pct"]]
        .rename(
            columns={
                dim: dim_label,
                "Qty": "Units",
                "net_revenue": "Net revenue",
                "gross_profit": "Gross profit",
                "margin_pct": "Margin %",
                "share_pct": "Share %",
            }
        )
        .style.format(
            {
                "Units": "{:,.0f}",
                "Net revenue": "{:,.0f}",
                "Gross profit": "{:,.0f}",
                "Margin %": "{:.1f}",
                "Share %": "{:.1f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.divider()


# --------------------------------------------------------------------------
# Actual vs target
# --------------------------------------------------------------------------
st.subheader("Actual vs target")
st.caption(metrics.coverage_note(fact, targets))

avt = metrics.actual_vs_target(fact, targets, measure="Qty")

if avt.empty:
    st.info("No overlapping months between the filtered transactions and targets.")
else:
    c1, c2 = st.columns(2)

    with c1:
        # Two series in the same unit, so one axis is correct - never a
        # second y-scale. Legend present because there are two series.
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=avt["Month"], y=avt["actual"], mode="lines", name="Actual",
                line=dict(color=theme.CATEGORICAL_LIGHT[0], width=2),
                hovertemplate="%{x|%b %Y}<br>Actual %{y:,.0f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=avt["Month"], y=avt["target"], mode="lines", name="Target",
                line=dict(color=theme.TEXT_MUTED, width=2, dash="dot"),
                hovertemplate="%{x|%b %Y}<br>Target %{y:,.0f}<extra></extra>",
            )
        )
        fig.update_layout(hovermode="x unified")
        theme.apply_layout(fig, height=300, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        # Above/below a baseline is the diverging job: two poles, zero line.
        colors = [
            theme.DIVERGING_POSITIVE if v >= 0 else theme.DIVERGING_NEGATIVE
            for v in avt["variance"]
        ]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=avt["Month"], y=avt["variance"],
                marker=dict(color=colors, line=dict(color=theme.SURFACE, width=2)),
                hovertemplate="%{x|%b %Y}<br>Variance %{y:,.0f}<extra></extra>",
            )
        )
        fig.add_hline(y=0, line_color=theme.BASELINE, line_width=1)
        theme.apply_layout(fig, height=300)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Units above (blue) or below (red) target")

    total_actual = avt["actual"].sum()
    total_target = avt["target"].sum()
    st.metric(
        "Achievement",
        f"{total_actual / total_target * 100:.1f}%" if total_target else "n/a",
        delta=f"{total_actual - total_target:,.0f} units vs target",
    )

    with st.expander("Table - actual vs target by month"):
        st.dataframe(
            avt.assign(Month=avt["Month"].dt.strftime("%b %Y"))
            .rename(
                columns={
                    "actual": "Actual units",
                    "target": "Target",
                    "variance": "Variance",
                    "achievement_pct": "Achievement %",
                }
            )
            .style.format(
                {
                    "Actual units": "{:,.0f}",
                    "Target": "{:,.0f}",
                    "Variance": "{:,.0f}",
                    "Achievement %": "{:.1f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
