"""poc_bi - sales performance BI proof of concept.

Layers, bottom up:

    data     loading and cleaning; all raw-CSV quirks are handled here
    metrics  aggregations over a clean fact table; no IO, no plotting
    theme    chart palette and Plotly chrome

The Streamlit app in app.py is one consumer of these. A notebook, an Excel
export or a different front end are equally valid consumers - keep business
logic in metrics, not in the app.
"""

from poc_bi.data import (
    DataPaths,
    build_fact,
    build_target_fact,
    load_customers,
    load_products,
    load_targets,
    load_transactions,
    normalize_id,
)

__all__ = [
    "DataPaths",
    "build_fact",
    "build_target_fact",
    "load_customers",
    "load_products",
    "load_targets",
    "load_transactions",
    "normalize_id",
]
