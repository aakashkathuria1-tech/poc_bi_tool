"""Tests for the aggregation layer.

Built on small hand-made frames where the right answer is obvious by
inspection, so a failure points at the calculation rather than at the sample
data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from poc_bi import data, metrics


def make_fact() -> pd.DataFrame:
    """Two customers, two products, two months, arithmetic that checks by eye."""
    raw = pd.DataFrame(
        {
            "Cust_ID": ["C001", "C001", "C002", "C002"],
            "Prod_ID": ["P001", "P002", "P001", "P002"],
            "Date": pd.to_datetime(
                ["2024-04-05", "2024-04-20", "2024-05-05", "2024-05-20"]
            ),
            "Order No": ["O1", "O2", "O3", "O4"],
            "Qty": [2, 3, 4, 1],
            "MRP": [100.0, 100.0, 50.0, 200.0],
            "Cost": [60.0, 60.0, 30.0, 120.0],
            "Discount": [0.0, 0.10, 0.0, 0.50],
            "region": ["North", "North", "South", "South"],
            "category": ["Electronics", "Home", "Electronics", "Home"],
        }
    )
    raw["Month"] = raw["Date"].values.astype("datetime64[M]")
    return data.add_measures(raw)


def make_targets() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Cust_ID": ["C001", "C002"],
            "Prod_ID": ["P001", "P001"],
            "Month": pd.to_datetime(["2024-04-01", "2024-05-01"]),
            "Target": [10.0, 2.0],
            "region": ["North", "South"],
            "category": ["Electronics", "Electronics"],
        }
    )


class TestHeadlineKpis:
    def test_totals(self):
        k = metrics.headline_kpis(make_fact())
        # gross: 200 + 300 + 200 + 200 = 900
        assert k["gross_revenue"] == pytest.approx(900.0)
        # net: 200 + 270 + 200 + 100 = 770
        assert k["net_revenue"] == pytest.approx(770.0)
        assert k["units"] == pytest.approx(10.0)
        assert k["orders"] == pytest.approx(4.0)

    def test_margin_is_recomputed_not_averaged(self):
        """A mean of per-row margins would give a different, wrong answer."""
        fact = make_fact()
        k = metrics.headline_kpis(fact)
        # cogs: 120 + 180 + 120 + 120 = 540; profit = 770 - 540 = 230
        assert k["gross_profit"] == pytest.approx(230.0)
        assert k["margin_pct"] == pytest.approx(230.0 / 770.0 * 100)

        per_row_mean = (fact["gross_profit"] / fact["net_revenue"] * 100).mean()
        assert k["margin_pct"] != pytest.approx(per_row_mean)

    def test_empty_frame_does_not_divide_by_zero(self):
        k = metrics.headline_kpis(make_fact().iloc[0:0])
        assert k["margin_pct"] == 0.0
        assert k["avg_order_value"] == 0.0


class TestBreakdown:
    def test_sorted_by_measure_descending(self):
        out = metrics.breakdown(make_fact(), "region")
        assert list(out["region"]) == ["North", "South"]
        assert out["net_revenue"].is_monotonic_decreasing

    def test_shares_sum_to_100(self):
        out = metrics.breakdown(make_fact(), "category")
        assert out["share_pct"].sum() == pytest.approx(100.0)

    def test_top_n_folds_tail_into_other_without_losing_total(self):
        fact = make_fact()
        full = metrics.breakdown(fact, "Cust_ID")
        folded = metrics.breakdown(fact, "Cust_ID", top_n=1)
        assert "Other" in list(folded["Cust_ID"])
        assert folded["net_revenue"].sum() == pytest.approx(full["net_revenue"].sum())

    def test_top_n_noop_when_under_limit(self):
        out = metrics.breakdown(make_fact(), "region", top_n=10)
        assert "Other" not in list(out["region"])

    def test_unknown_dimension_raises(self):
        with pytest.raises(KeyError):
            metrics.breakdown(make_fact(), "not_a_column")


class TestMonthlyTrend:
    def test_one_row_per_month_in_order(self):
        out = metrics.monthly_trend(make_fact())
        assert len(out) == 2
        assert out["Month"].is_monotonic_increasing

    def test_month_totals(self):
        out = metrics.monthly_trend(make_fact())
        assert out.iloc[0]["net_revenue"] == pytest.approx(470.0)  # 200 + 270
        assert out.iloc[1]["net_revenue"] == pytest.approx(300.0)  # 200 + 100


class TestActualVsTarget:
    def test_clips_to_overlapping_months(self):
        """Actuals outside the target window must not score against zero."""
        fact = make_fact()
        targets = make_targets().head(1)  # April only
        out = metrics.actual_vs_target(fact, targets)
        assert len(out) == 1
        assert out.iloc[0]["Month"] == pd.Timestamp("2024-04-01")
        assert out.attrs["window_start"] == pd.Timestamp("2024-04-01")

    def test_variance_and_achievement(self):
        out = metrics.actual_vs_target(make_fact(), make_targets())
        april = out[out["Month"] == pd.Timestamp("2024-04-01")].iloc[0]
        assert april["actual"] == pytest.approx(5.0)  # 2 + 3 units
        assert april["target"] == pytest.approx(10.0)
        assert april["variance"] == pytest.approx(-5.0)
        assert april["achievement_pct"] == pytest.approx(50.0)

    def test_zero_target_does_not_produce_inf(self):
        targets = make_targets()
        targets.loc[0, "Target"] = 0.0
        out = metrics.actual_vs_target(make_fact(), targets)
        assert out["achievement_pct"].notna().all()
        assert not (out["achievement_pct"] == float("inf")).any()

    def test_groups_by_dimension(self):
        out = metrics.actual_vs_target(make_fact(), make_targets(), dimension="region")
        assert set(out["region"]) == {"North", "South"}

    def test_no_overlap_returns_empty(self):
        targets = make_targets()
        targets["Month"] = pd.to_datetime(["2030-01-01", "2030-02-01"])
        assert metrics.actual_vs_target(make_fact(), targets).empty


class TestFilterFact:
    def test_no_filters_is_identity(self):
        fact = make_fact()
        assert len(metrics.filter_fact(fact)) == len(fact)

    def test_region_filter(self):
        out = metrics.filter_fact(make_fact(), regions=["North"])
        assert set(out["region"]) == {"North"}

    def test_date_bounds_are_inclusive(self):
        out = metrics.filter_fact(
            make_fact(),
            date_from=pd.Timestamp("2024-04-05"),
            date_to=pd.Timestamp("2024-04-05"),
        )
        assert len(out) == 1

    def test_filters_combine(self):
        out = metrics.filter_fact(
            make_fact(), regions=["North"], categories=["Electronics"]
        )
        assert len(out) == 1


class TestCoverageNote:
    def test_states_the_window(self):
        note = metrics.coverage_note(make_fact(), make_targets())
        assert "Apr 2024" in note and "May 2024" in note

    def test_handles_no_overlap(self):
        targets = make_targets()
        targets["Month"] = pd.to_datetime(["2030-01-01", "2030-02-01"])
        assert "No overlapping period" in metrics.coverage_note(make_fact(), targets)
