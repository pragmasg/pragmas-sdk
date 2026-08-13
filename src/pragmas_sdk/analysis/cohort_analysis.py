"""
Cohort retention analysis for any recurring-revenue business.

Input (CSV of transactions/activity), required columns:
    customer_id, date, revenue
(one row per transaction or billing/usage event — SaaS invoices,
subscription charges, repeat-service visits, etc.)

Params:
    horizon_months: how many month_indices to compute/chart, starting
        at 0 (default 12) — same role as ecommerce_unit_economics'
        ltv_horizon_months.

Output (results):
    cohort_months: sorted list of cohort labels present in the data
        (e.g. "2026-01"), one per calendar month of first activity.
    horizon_months: the horizon actually used (int).
    cohorts: dict keyed by cohort month string, each value:
        customer_count:        size of the cohort (distinct customers
            whose first-ever row falls in that month).
        revenue_by_month_index: list of floats, index 0 = that cohort's
            total revenue in its own first month, index 1 = its second
            month, etc., up to horizon_months (NOT cumulative).
        revenue_retention_pct: list of floats, each month_index's cohort
            revenue as a % of that same cohort's own month-0 revenue
            (month 0 is always 100.0).
        customer_retention_pct: list of floats, % of the cohort's
            original customers who had ANY row (any revenue, including
            zero) in that month_index — logo/customer retention, not
            revenue retention.
Chart: overlapping revenue-retention curves, one line per cohort
    (cohort_retention.png).

vs `ecommerce_unit_economics`: use THIS template for cohort retention
analysis on any recurring-revenue business without needing product/channel
breakdown or CAC data. Use `ecommerce_unit_economics` when you need LTV
broken down by product/channel alongside CAC/breakeven-ROAS — its cohort
logic is ecommerce-order-specific (assumes order_id/product/channel
columns and computes cumulative LTV, not month-over-month retention).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from pragmas_sdk.analysis.base import (
    AnalysisInputError,
    load_csv,
    package_result,
    save_chart,
)

MODULE = "cohort_analysis"
REQUIRED_COLS = ["customer_id", "date", "revenue"]
KNOWN_PARAMS = frozenset({"horizon_months"})


def run_cohort_analysis(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    params = params or {}
    try:
        df = load_csv(input_csv, REQUIRED_COLS, parse_dates=["date"])
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
        if df["revenue"].isna().any():
            raise AnalysisInputError("Column 'revenue' contains non-numeric values")
        df["revenue"] = df["revenue"].astype(float)

        horizon = int(params.get("horizon_months", 12))

        df["cohort"] = (
            df.groupby("customer_id")["date"].transform("min").dt.to_period("M").astype(str)
        )
        cohort_months = sorted(df["cohort"].unique())
        if len(cohort_months) < 2:
            raise AnalysisInputError(
                "At least 2 distinct cohort months (customers with different "
                "first-activity months) are required"
            )

        df["month_index"] = (
            (df["date"].dt.year - pd.PeriodIndex(df["cohort"], freq="M").year) * 12
            + (df["date"].dt.month - pd.PeriodIndex(df["cohort"], freq="M").month)
        )

        cohort_sizes = df.groupby("cohort")["customer_id"].nunique()

        windowed = df[df["month_index"] < horizon]

        revenue_pivot = (
            windowed.groupby(["cohort", "month_index"])["revenue"]
            .sum()
            .unstack(fill_value=0.0)
            .reindex(index=cohort_months, columns=range(horizon), fill_value=0.0)
        )

        active_customers_pivot = (
            windowed.groupby(["cohort", "month_index"])["customer_id"]
            .nunique()
            .unstack(fill_value=0)
            .reindex(index=cohort_months, columns=range(horizon), fill_value=0)
        )
        customer_retention_pivot = active_customers_pivot.div(cohort_sizes, axis=0) * 100

        month0 = revenue_pivot[0] if 0 in revenue_pivot.columns else pd.Series(
            0.0, index=cohort_months
        )
        revenue_retention_pivot = revenue_pivot.div(month0.replace(0, np.nan), axis=0) * 100
        revenue_retention_pivot = revenue_retention_pivot.fillna(0.0)

        cohorts: Dict[str, Any] = {}
        for cohort in cohort_months:
            cohorts[str(cohort)] = {
                "customer_count": int(cohort_sizes[cohort]),
                "revenue_by_month_index": [float(x) for x in revenue_pivot.loc[cohort]],
                "revenue_retention_pct": [float(x) for x in revenue_retention_pivot.loc[cohort]],
                "customer_retention_pct": [float(x) for x in customer_retention_pivot.loc[cohort]],
            }

        charts = []
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 5))
        for cohort in cohort_months:
            row = revenue_retention_pivot.loc[cohort]
            ax.plot(range(len(row)), row.values, marker="o", markersize=3, label=str(cohort))
        ax.set_title("Revenue retention by cohort")
        ax.set_xlabel("Months since cohort's first activity")
        ax.set_ylabel("Revenue retention %")
        ax.legend(fontsize=7, ncol=2 if len(cohort_months) > 6 else 1)
        charts.append(save_chart(fig, output_dir, "cohort_retention"))

        results = {
            "cohort_months": [str(c) for c in cohort_months],
            "horizon_months": horizon,
            "cohorts": cohorts,
        }
        return package_result(MODULE, output_dir, results, charts)

    except AnalysisInputError as exc:
        return package_result(MODULE, output_dir, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — module must never raise to the caller
        return package_result(MODULE, output_dir, error=f"Unexpected error: {exc}")
