"""Tests for the loading/cleaning layer.

These exist mostly as regression cover for the raw-CSV quirks. Each one
protects against a silent-wrong-answer bug, not a crash - which is exactly the
kind that survives to a stakeholder demo.
"""

from __future__ import annotations

import pandas as pd
import pytest

from poc_bi import data


@pytest.fixture(scope="module")
def paths() -> data.DataPaths:
    p = data.DataPaths.samples()
    missing = p.missing()
    if missing:
        pytest.skip(f"sample data not present: {missing}")
    return p


@pytest.fixture(scope="module")
def fact(paths: data.DataPaths) -> pd.DataFrame:
    return data.build_fact(paths)


class TestNormalizeId:
    def test_collapses_inconsistent_padding(self):
        got = data.normalize_id(pd.Series(["C001", "C0010", "C10", "C1"]))
        assert list(got) == ["C001", "C010", "C010", "C001"]

    def test_preserves_prefix_letter(self):
        got = data.normalize_id(pd.Series(["P007", "C007"]))
        assert list(got) == ["P007", "C007"]

    def test_tolerates_whitespace(self):
        assert data.normalize_id(pd.Series([" C001 "])).iloc[0] == "C001"

    def test_unparseable_becomes_null(self):
        assert pd.isna(data.normalize_id(pd.Series(["Cxx"])).iloc[0])


class TestTransactions:
    def test_blank_final_row_is_dropped(self, paths):
        """The blank row carries a value in the counter column.

        It only looks blank once that column is gone, so dropping rows before
        dropping the column leaves it in the frame - with a null Cust_ID that
        quietly becomes an unmatched row downstream.
        """
        df = data.load_transactions(paths)
        assert df["Cust_ID"].notna().all()
        assert df["Date"].notna().all()
        assert len(df) == 100_338

    def test_counter_column_is_gone(self, paths):
        df = data.load_transactions(paths)
        assert not [c for c in df.columns if str(c).startswith("Unnamed")]

    def test_excel_serial_becomes_real_dates(self, paths):
        df = data.load_transactions(paths)
        assert df["Date"].min() == pd.Timestamp("2024-01-01")
        assert df["Date"].max() == pd.Timestamp("2026-12-30")

    def test_month_is_start_of_month(self, paths):
        df = data.load_transactions(paths)
        assert (df["Month"].dt.day == 1).all()


class TestJoins:
    def test_no_orphan_rows_after_normalization(self, fact):
        """The C0010-vs-C010 mismatch would drop these silently."""
        assert fact["region"].notna().all()
        assert fact["category"].notna().all()

    def test_tenth_members_survive_the_join(self, fact):
        """The specific members a naive join loses."""
        assert (fact["Cust_ID"] == "C010").any()
        assert (fact["Prod_ID"] == "P010").any()
        assert fact.loc[fact["Cust_ID"] == "C010", "region"].eq("East").all()

    def test_join_does_not_duplicate_rows(self, paths, fact):
        assert len(fact) == len(data.load_transactions(paths))

    def test_all_ten_of_each_present(self, fact):
        assert fact["Cust_ID"].nunique() == 10
        assert fact["Prod_ID"].nunique() == 10


class TestMeasures:
    def test_net_is_gross_less_discount(self, fact):
        row = fact.iloc[0]
        assert row["net_revenue"] == pytest.approx(
            row["gross_revenue"] * (1 - row["Discount"])
        )

    def test_gross_revenue_is_qty_times_mrp(self, fact):
        row = fact.iloc[0]
        assert row["gross_revenue"] == pytest.approx(row["Qty"] * row["MRP"])

    def test_profit_is_net_less_cogs(self, fact):
        row = fact.iloc[0]
        assert row["gross_profit"] == pytest.approx(row["net_revenue"] - row["cogs"])

    def test_discount_value_reconciles(self, fact):
        assert fact["discount_value"].sum() == pytest.approx(
            fact["gross_revenue"].sum() - fact["net_revenue"].sum()
        )

    def test_no_negative_revenue(self, fact):
        assert (fact["net_revenue"] >= 0).all()


class TestTargets:
    def test_month_parses(self, paths):
        df = data.load_targets(paths)
        assert df["Month"].min() == pd.Timestamp("2024-04-01")
        assert df["Month"].max() == pd.Timestamp("2025-12-01")

    def test_grain_is_unique(self, paths):
        df = data.load_targets(paths)
        assert not df.duplicated(subset=["Cust_ID", "Prod_ID", "Month"]).any()

    def test_target_fact_joins_cleanly(self, paths):
        df = data.build_target_fact(paths)
        assert df["region"].notna().all()
        assert df["category"].notna().all()


class TestDataPaths:
    def test_missing_reports_absent_files(self, tmp_path):
        p = data.DataPaths.samples(root=tmp_path)
        assert len(p.missing()) == 4

    def test_samples_resolve_against_repo(self, paths):
        assert paths.missing() == []
