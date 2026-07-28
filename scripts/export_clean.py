"""Export the cleaned, joined data for Excel or Power BI.

The dashboard is one consumer of the data layer; this is another. If the POC
lands on Power BI or an Excel model instead of Streamlit, point it at these
outputs rather than the raw CSVs - the quirks are already handled and the IDs
already join.

Usage (from the repo root, venv active):

    python scripts\\export_clean.py                # -> output\\ as .xlsx
    python scripts\\export_clean.py --format csv
    python scripts\\export_clean.py --out C:\\reports
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402

from poc_bi import data, metrics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=Path("output"), help="output directory"
    )
    parser.add_argument(
        "--format", choices=("xlsx", "csv"), default="xlsx", help="output format"
    )
    args = parser.parse_args()

    paths = data.DataPaths.samples()
    if missing := paths.missing():
        sys.exit("Missing data file(s): " + ", ".join(str(p) for p in missing))

    fact = data.build_fact(paths)
    targets = data.build_target_fact(paths)

    sheets = {
        "fact_sales": fact,
        "targets": targets,
        "monthly_trend": metrics.monthly_trend(fact),
        "by_region": metrics.breakdown(fact, "region"),
        "by_category": metrics.breakdown(fact, "category"),
        "by_customer": metrics.breakdown(fact, "Cust_ID"),
        "by_product": metrics.breakdown(fact, "Prod_ID"),
        "actual_vs_target": metrics.actual_vs_target(fact, targets),
    }

    args.out.mkdir(parents=True, exist_ok=True)

    if args.format == "csv":
        for name, df in sheets.items():
            dest = args.out / f"{name}.csv"
            df.to_csv(dest, index=False)
            print(f"  {dest}  ({len(df):,} rows)")
    else:
        dest = args.out / "poc_bi_clean.xlsx"
        # Excel caps a sheet at 1,048,576 rows; the fact table is well under
        # that, but check rather than silently truncate if real data is larger.
        for name, df in sheets.items():
            if len(df) > 1_048_575:
                sys.exit(
                    f"{name} has {len(df):,} rows, too many for one Excel sheet. "
                    "Re-run with --format csv."
                )
        with pd.ExcelWriter(dest, engine="openpyxl") as writer:
            for name, df in sheets.items():
                df.to_excel(writer, sheet_name=name[:31], index=False)
                print(f"  {name}  ({len(df):,} rows)")
        print(f"\nWrote {dest}")

    print(f"\n{metrics.coverage_note(fact, targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
