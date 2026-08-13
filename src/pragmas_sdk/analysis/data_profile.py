"""
Generic CSV profiler — PRAGMAS' "hello world for datasets".

Unlike the other templates in this package, `data_profile` has NO fixed
required columns: it runs on any CSV, with any (or no) params, and
describes the shape of the data rather than computing a domain-specific
metric.

Input: any CSV.
Params: none read today — `KNOWN_PARAMS` is intentionally empty. The
    parameter is still accepted (and ignored) so the module has the same
    call signature as every other template.

Output (results) — top-level keys:
    row_count:    int, number of data rows.
    column_count: int, number of columns.
    columns: dict of column_name -> {
        "missing_count":  int, number of null/NaN cells in that column.
        "missing_pct":    float, missing_count / row_count * 100.
        "unique_count":   int, number of distinct non-null values.
        "inferred_type":  one of "numeric" / "date" / "categorical" /
            "id-like". Best-effort only (see heuristics below) — this is
            a descriptive hint, not a schema guarantee.
    }
    duplicate_row_count: int, `df.duplicated().sum()` — exact full-row
        duplicates only.
    correlation_matrix: nested dict {col: {col2: corr}} over columns
        inferred as "numeric" (id-like numeric columns, e.g. an integer
        primary key, are excluded on purpose — correlating an ID against
        other columns is not meaningful). Empty dict when fewer than 2
        numeric columns exist.
    outliers: dict of numeric_column -> count of values outside
        [Q1 - 1.5*IQR, Q3 + 1.5*IQR] (same IQR method as
        `r_templates/outliers.R`, computed here in pandas — no R needed).
        Only covers columns inferred as "numeric" (same exclusion of
        id-like columns as the correlation matrix).
    potential_id_columns: list of column names inferred as "id-like".
    potential_date_columns: list of column names inferred as "date".
    potential_categorical_columns: list of column names inferred as
        "categorical".

Type-inference heuristics (best-effort, in priority order — first match
wins per column, evaluated over non-null values only):
    1. numeric: >=95% of non-null values parse via `pd.to_numeric`. If,
       in addition, unique_count / row_count > 0.95, the column is
       reclassified "id-like" instead (catches integer primary keys —
       a sequential int column carries no more information than a
       string ID would).
    2. date: (only checked once numeric is ruled out, so plain integers
       don't get misread as nanosecond epoch timestamps) >=95% of
       non-null values parse via `pd.to_datetime`. Near-unique date/
       timestamp columns are intentionally left as "date", not
       "id-like" — that's the common case for per-row timestamps and
       is more informative than lumping them in with ID columns.
    3. id-like: for anything neither numeric nor date, unique_count /
       row_count > 0.95 (needs at least 2 rows) — catches
       non-numeric ID shapes such as UUIDs or order codes.
    4. categorical: fallback for everything else (including all-null
       columns, which can't be inferred at all).
    None of this is a precision-guaranteed type system — e.g. a
    continuous numeric column that happens to have almost no repeated
    values (like a "price" column with few duplicates) can be
    misclassified as "id-like", and short date ranges can look
    "categorical" if `pd.to_datetime` can't parse the format. Treat
    "potential" in the list names literally.

Chart: one missing-values-by-column bar chart (`save_chart(...,
"missing_values")`), included only when at least one cell in the whole
CSV is missing. If there are zero missing values, `results["charts"]`
correctly ends up as an empty list — that's a valid, non-error outcome,
not a skipped chart.

Explicitly out of scope for this template (by design, not a gap):
    - No histograms or other charts beyond the single missing-values bar
      chart.
    - No data imputation, cleaning, or automatic type coercion of the
      source data — this is a read-only, purely descriptive profiler.
      The source CSV is never modified and inferred types are never
      written back into it.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from pragmas_sdk.analysis.base import (
    AnalysisInputError,
    load_csv,
    package_result,
    save_chart,
)

MODULE = "data_profile"
REQUIRED_COLS: list = []
KNOWN_PARAMS: frozenset[str] = frozenset()

_ID_LIKE_UNIQUE_RATIO = 0.95
_TYPE_PARSE_RATIO = 0.95


def _infer_column_type(series: pd.Series, row_count: int) -> str:
    """Best-effort type inference for one column. See module docstring
    for the exact heuristic and its known false-positive cases."""
    non_null = series.dropna()
    n = len(non_null)
    if n == 0:
        return "categorical"

    unique_count = non_null.nunique()
    unique_ratio = (unique_count / row_count) if row_count > 1 else 0.0

    numeric = pd.to_numeric(non_null, errors="coerce")
    if (numeric.notna().sum() / n) >= _TYPE_PARSE_RATIO:
        return "id-like" if unique_ratio > _ID_LIKE_UNIQUE_RATIO else "numeric"

    with warnings.catch_warnings():
        # Best-effort format inference across mixed/ambiguous string dates
        # is expected here — this is a heuristic, not a strict parser.
        warnings.simplefilter("ignore", UserWarning)
        dates = pd.to_datetime(non_null, errors="coerce")
    if (dates.notna().sum() / n) >= _TYPE_PARSE_RATIO:
        return "date"

    if unique_ratio > _ID_LIKE_UNIQUE_RATIO:
        return "id-like"

    return "categorical"


def run_data_profile(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    params = params or {}
    try:
        df = load_csv(input_csv, REQUIRED_COLS)

        row_count = int(len(df))
        column_count = int(len(df.columns))

        columns: Dict[str, Dict[str, Any]] = {}
        for col in df.columns:
            series = df[col]
            missing_count = int(series.isna().sum())
            missing_pct = (missing_count / row_count * 100) if row_count else 0.0
            unique_count = int(series.dropna().nunique())
            inferred_type = _infer_column_type(series, row_count)
            columns[col] = {
                "missing_count": missing_count,
                "missing_pct": missing_pct,
                "unique_count": unique_count,
                "inferred_type": inferred_type,
            }

        duplicate_row_count = int(df.duplicated().sum())

        numeric_cols = [c for c, info in columns.items() if info["inferred_type"] == "numeric"]

        correlation_matrix: Dict[str, Dict[str, float]] = {}
        if len(numeric_cols) >= 2:
            numeric_df = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
            corr = numeric_df.corr()
            correlation_matrix = {
                col: {other: float(corr.loc[col, other]) for other in corr.columns}
                for col in corr.index
            }

        outliers: Dict[str, int] = {}
        for col in numeric_cols:
            values = pd.to_numeric(df[col], errors="coerce").dropna()
            if values.empty:
                outliers[col] = 0
                continue
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outliers[col] = int(((values < lower) | (values > upper)).sum())

        potential_id_columns = [c for c, info in columns.items() if info["inferred_type"] == "id-like"]
        potential_date_columns = [c for c, info in columns.items() if info["inferred_type"] == "date"]
        potential_categorical_columns = [
            c for c, info in columns.items() if info["inferred_type"] == "categorical"
        ]

        charts = []
        total_missing = sum(info["missing_count"] for info in columns.values())
        if total_missing > 0:
            import matplotlib.pyplot as plt

            cols_with_missing = [c for c, info in columns.items() if info["missing_count"] > 0]
            counts = [columns[c]["missing_count"] for c in cols_with_missing]
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(cols_with_missing, counts, color="#C62828")
            ax.set_title("Missing values by column")
            ax.set_ylabel("Missing count")
            ax.tick_params(axis="x", rotation=45, labelsize=8)
            charts.append(save_chart(fig, output_dir, "missing_values"))

        results = {
            "row_count": row_count,
            "column_count": column_count,
            "columns": columns,
            "duplicate_row_count": duplicate_row_count,
            "correlation_matrix": correlation_matrix,
            "outliers": outliers,
            "potential_id_columns": potential_id_columns,
            "potential_date_columns": potential_date_columns,
            "potential_categorical_columns": potential_categorical_columns,
        }
        return package_result(MODULE, output_dir, results, charts)

    except AnalysisInputError as exc:
        return package_result(MODULE, output_dir, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return package_result(MODULE, output_dir, error=f"Unexpected error: {exc}")
