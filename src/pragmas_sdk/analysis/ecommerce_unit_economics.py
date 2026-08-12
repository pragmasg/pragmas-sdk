"""
Unit economics for e-commerce.

Input (CSV of orders), required columns:
    order_id, date, customer_id, product, channel, revenue, cogs
Optional: shipping_cost, other_variable_costs

Params:
    ad_spend_by_channel: {channel: total_ad_spend}  (for CAC and ROAS)
    ltv_horizon_months:  months in the per-cohort LTV curve (default 12)

Output (results):
    contribution_by_product / contribution_by_channel:
        revenue, variable_costs, contribution, margin_pct
    cac_by_channel: spend / new customers acquired through that channel
    breakeven_roas_by_channel: 1 / contribution margin ratio
    ltv_by_cohort: cumulative contribution margin per customer,
        cohorts by month of first purchase
Charts: margin by product (bar), LTV curves by cohort.
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

MODULE = "ecommerce_unit_economics"
REQUIRED_COLS = ["order_id", "date", "customer_id", "product", "channel", "revenue", "cogs"]


def run_ecommerce_unit_economics(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    params = params or {}
    try:
        df = load_csv(input_csv, REQUIRED_COLS, parse_dates=["date"])

        for col in ("shipping_cost", "other_variable_costs"):
            if col not in df.columns:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        for col in ("revenue", "cogs"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if df["revenue"].isna().any() or df["cogs"].isna().any():
            raise AnalysisInputError("revenue/cogs contain non-numeric values")

        df["variable_costs"] = df["cogs"] + df["shipping_cost"] + df["other_variable_costs"]
        df["contribution"] = df["revenue"] - df["variable_costs"]

        def _margin_table(group_col: str) -> Dict[str, Dict[str, float]]:
            g = df.groupby(group_col).agg(
                revenue=("revenue", "sum"),
                variable_costs=("variable_costs", "sum"),
                contribution=("contribution", "sum"),
                orders=("order_id", "nunique"),
            )
            g["margin_pct"] = np.where(
                g["revenue"] != 0, g["contribution"] / g["revenue"] * 100, 0.0
            )
            return {str(k): v for k, v in g.round(4).to_dict(orient="index").items()}

        by_product = _margin_table("product")
        by_channel = _margin_table("channel")

        # CAC and break-even ROAS per channel (channel of first purchase)
        ad_spend = {str(k): float(v) for k, v in (params.get("ad_spend_by_channel") or {}).items()}
        first_orders = df.sort_values("date").drop_duplicates("customer_id", keep="first")
        new_customers = first_orders.groupby("channel")["customer_id"].nunique()

        cac_by_channel: Dict[str, Any] = {}
        breakeven_roas: Dict[str, Any] = {}
        for channel, stats in by_channel.items():
            spend = ad_spend.get(channel)
            n_new = int(new_customers.get(channel, 0))
            cac_by_channel[channel] = {
                "ad_spend": spend,
                "new_customers": n_new,
                "cac": (spend / n_new) if spend is not None and n_new else None,
            }
            margin_ratio = stats["contribution"] / stats["revenue"] if stats["revenue"] else 0.0
            # Minimum ROAS for zero contribution: revenue/spend = 1/margin ratio
            breakeven_roas[channel] = (1.0 / margin_ratio) if margin_ratio > 0 else None

        # LTV by cohort: cumulative contribution margin per customer
        horizon = int(params.get("ltv_horizon_months", 12))
        df["cohort"] = (
            df.groupby("customer_id")["date"].transform("min").dt.to_period("M").astype(str)
        )
        df["month_index"] = (
            (df["date"].dt.year - pd.PeriodIndex(df["cohort"], freq="M").year) * 12
            + (df["date"].dt.month - pd.PeriodIndex(df["cohort"], freq="M").month)
        )
        cohort_sizes = df.groupby("cohort")["customer_id"].nunique()
        pivot = (
            df[df["month_index"] < horizon]
            .groupby(["cohort", "month_index"])["contribution"]
            .sum()
            .unstack(fill_value=0.0)
            .reindex(columns=range(horizon), fill_value=0.0)
        )
        ltv_curves = pivot.cumsum(axis=1).div(cohort_sizes, axis=0)

        ltv_by_cohort = {
            str(cohort): {
                "customers": int(cohort_sizes[cohort]),
                "ltv_curve": [float(x) for x in row],
                "ltv": float(row.iloc[-1]),
            }
            for cohort, row in ltv_curves.iterrows()
        }

        charts = []
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 5))
        products = list(by_product)
        margins = [by_product[p]["contribution"] for p in products]
        ax.bar(products, margins, color="#1F3A5F")
        ax.set_title("Contribution margin by product")
        ax.set_ylabel("Contribution")
        ax.tick_params(axis="x", rotation=45)
        charts.append(save_chart(fig, output_dir, "contribution_by_product"))

        fig, ax = plt.subplots(figsize=(9, 5))
        for cohort, row in ltv_curves.iterrows():
            ax.plot(range(len(row)), row.values, marker="o", markersize=3, label=str(cohort))
        ax.set_title("Cumulative LTV by cohort (contribution margin)")
        ax.set_xlabel("Months since first purchase")
        ax.set_ylabel("LTV")
        ax.legend(fontsize=7, ncol=2)
        charts.append(save_chart(fig, output_dir, "ltv_by_cohort"))

        results = {
            "orders": int(df["order_id"].nunique()),
            "customers": int(df["customer_id"].nunique()),
            "total_revenue": float(df["revenue"].sum()),
            "total_contribution": float(df["contribution"].sum()),
            "contribution_by_product": by_product,
            "contribution_by_channel": by_channel,
            "cac_by_channel": cac_by_channel,
            "breakeven_roas_by_channel": breakeven_roas,
            "ltv_by_cohort": ltv_by_cohort,
        }
        return package_result(MODULE, output_dir, results, charts)

    except AnalysisInputError as exc:
        return package_result(MODULE, output_dir, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — module must never raise to the caller
        return package_result(MODULE, output_dir, error=f"Unexpected error: {exc}")
