"""
SaaS metrics.

Input (CSV of monthly subscriptions), required columns:
    customer_id, month (YYYY-MM), mrr
(one row per customer per month with that month's MRR)

Params:
    gross_margin:      gross margin 0-1 (default 0.8)
    cac:               average CAC (currency/customer) — for payback and LTV/CAC
    ebitda_margin_pct: EBITDA margin % for Rule of 40 (default 0)

Output (results):
    mrr_bridge: per month — starting, new, expansion, contraction,
        churned, ending
    churn: per month — customer_churn_pct vs revenue_churn_pct (gross)
    cac_payback_months, ltv, ltv_cac_ratio
    rule_of_40: annualized MRR growth % + EBITDA margin %
Charts: MRR bridge (stacked bars), customer vs revenue churn.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from pragmas_sdk.analysis.base import (
    AnalysisInputError,
    load_csv,
    package_result,
    save_chart,
)

MODULE = "saas_metrics"
REQUIRED_COLS = ["customer_id", "month", "mrr"]


def run_saas_metrics(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    params = params or {}
    try:
        df = load_csv(input_csv, REQUIRED_COLS)
        df["mrr"] = pd.to_numeric(df["mrr"], errors="coerce")
        if df["mrr"].isna().any():
            raise AnalysisInputError("Column 'mrr' contains non-numeric values")
        try:
            df["month"] = pd.PeriodIndex(df["month"].astype(str), freq="M")
        except Exception as exc:
            raise AnalysisInputError(f"Invalid month format (expected YYYY-MM): {exc}") from exc

        df = df.groupby(["customer_id", "month"], as_index=False)["mrr"].sum()
        months = sorted(df["month"].unique())
        if len(months) < 2:
            raise AnalysisInputError("At least 2 months of data are required")

        wide = df.pivot(index="customer_id", columns="month", values="mrr").fillna(0.0)
        wide = wide.reindex(columns=months, fill_value=0.0)

        bridge: Dict[str, Dict[str, float]] = {}
        churn: Dict[str, Dict[str, float]] = {}
        for prev, curr in zip(months[:-1], months[1:]):
            p, c = wide[prev], wide[curr]
            new = c[(p == 0) & (c > 0)].sum()
            churned = -p[(p > 0) & (c == 0)].sum()
            active_both = (p > 0) & (c > 0)
            deltas = (c - p)[active_both]
            expansion = deltas[deltas > 0].sum()
            contraction = deltas[deltas < 0].sum()

            starting = float(p.sum())
            ending = float(c.sum())
            key = str(curr)
            bridge[key] = {
                "starting_mrr": starting,
                "new": float(new),
                "expansion": float(expansion),
                "contraction": float(contraction),
                "churned": float(churned),
                "ending_mrr": ending,
            }

            customers_start = int((p > 0).sum())
            churned_customers = int(((p > 0) & (c == 0)).sum())
            churn[key] = {
                "customer_churn_pct": (churned_customers / customers_start * 100) if customers_start else 0.0,
                "revenue_churn_pct": (-churned / starting * 100) if starting else 0.0,
            }

        last = months[-1]
        active_last = wide[last][wide[last] > 0]
        arpa = float(active_last.mean()) if len(active_last) else 0.0
        gross_margin = float(params.get("gross_margin", 0.8))
        cac = params.get("cac")
        cac = float(cac) if cac is not None else None

        avg_rev_churn = (
            sum(m["revenue_churn_pct"] for m in churn.values()) / len(churn) / 100
        )
        cac_payback = (
            cac / (arpa * gross_margin) if cac is not None and arpa * gross_margin > 0 else None
        )
        ltv = (arpa * gross_margin / avg_rev_churn) if avg_rev_churn > 0 else None
        ltv_cac = (ltv / cac) if ltv is not None and cac else None

        # Rule of 40: annualized MRR growth + EBITDA margin
        first_mrr = float(wide[months[0]].sum())
        last_mrr = float(wide[last].sum())
        n_periods = len(months) - 1
        if first_mrr > 0 and n_periods > 0:
            monthly_growth = (last_mrr / first_mrr) ** (1 / n_periods) - 1
            annualized_growth_pct = ((1 + monthly_growth) ** 12 - 1) * 100
        else:
            annualized_growth_pct = 0.0
        ebitda_margin_pct = float(params.get("ebitda_margin_pct", 0.0))
        rule_of_40 = annualized_growth_pct + ebitda_margin_pct

        charts = []
        import matplotlib.pyplot as plt
        import numpy as np

        keys = list(bridge)
        x = np.arange(len(keys))
        fig, ax = plt.subplots(figsize=(10, 5))
        news = [bridge[k]["new"] for k in keys]
        exps = [bridge[k]["expansion"] for k in keys]
        cons = [bridge[k]["contraction"] for k in keys]
        churns = [bridge[k]["churned"] for k in keys]
        ax.bar(x, news, label="New", color="#2E7D32")
        ax.bar(x, exps, bottom=news, label="Expansion", color="#81C784")
        ax.bar(x, cons, label="Contraction", color="#FFB74D")
        ax.bar(x, churns, bottom=cons, label="Churn", color="#C62828")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x, keys, rotation=45)
        ax.set_title("Monthly MRR bridge")
        ax.set_ylabel("Δ MRR")
        ax.legend(fontsize=8)
        charts.append(save_chart(fig, output_dir, "mrr_bridge"))

        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(keys, [churn[k]["customer_churn_pct"] for k in keys],
                marker="o", label="Customer churn %", color="#1F3A5F")
        ax.plot(keys, [churn[k]["revenue_churn_pct"] for k in keys],
                marker="s", label="Revenue churn %", color="#C62828")
        ax.set_title("Customer vs revenue churn")
        ax.set_ylabel("%")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=8)
        charts.append(save_chart(fig, output_dir, "churn_customers_vs_revenue"))

        results = {
            "months": [str(m) for m in months],
            "mrr_bridge": bridge,
            "churn": churn,
            "arpa": arpa,
            "gross_margin": gross_margin,
            "cac": cac,
            "cac_payback_months": cac_payback,
            "ltv": ltv,
            "ltv_cac_ratio": ltv_cac,
            "annualized_mrr_growth_pct": annualized_growth_pct,
            "ebitda_margin_pct": ebitda_margin_pct,
            "rule_of_40": rule_of_40,
        }
        return package_result(MODULE, output_dir, results, charts)

    except AnalysisInputError as exc:
        return package_result(MODULE, output_dir, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return package_result(MODULE, output_dir, error=f"Unexpected error: {exc}")
