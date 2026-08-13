"""
Board report — a curated, board-ready summary view over `saas_metrics`.

This template takes the EXACT same input as `saas_metrics` (CSV of monthly
subscriptions, one row per customer per month, columns: customer_id, month
(YYYY-MM), mrr) because it does not compute anything new: it runs
`run_saas_metrics` and then extracts/renames a curated subset of its output
into the handful of headline numbers a board deck needs (ending MRR/ARR,
growth, churn, Rule of 40, unit economics), while keeping the full
underlying results available for anyone who wants to drill in.

Params (identical meaning to `saas_metrics`'s own — passed straight
through unchanged):
    gross_margin:      gross margin 0-1 (default 0.8)
    cac:               average CAC (currency/customer) — for payback and
                        LTV/CAC
    ebitda_margin_pct: EBITDA margin % for Rule of 40 (default 0)

Output (results) — top-level keys:
    revenue:         {ending_mrr, arr} — ending_mrr is the last month's
        total MRR (mrr_bridge[<last month>]["ending_mrr"] from the
        underlying saas_metrics run), arr = ending_mrr * 12.
    growth:          {annualized_mrr_growth_pct} — pulled straight from
        the underlying saas_metrics results.
    churn:           {customer_churn_pct, revenue_churn_pct} for the most
        recent month, pulled from saas_metrics's per-month churn dict.
    rule_of_40:      pulled straight from the underlying saas_metrics
        results (annualized MRR growth % + EBITDA margin %).
    unit_economics:  {arpa, cac, cac_payback_months, ltv, ltv_cac_ratio}
        pulled from the underlying saas_metrics results. cac_payback_months,
        ltv and ltv_cac_ratio are null when no `cac` param was given,
        matching saas_metrics's own null-on-missing-cac behavior.
    details:         the FULL, unmodified results dict returned by
        run_saas_metrics, nested under this key — nothing is hidden, a
        caller can always drill into the complete underlying analysis
        (mrr_bridge, per-month churn, etc).
Charts: exactly the charts saas_metrics already produced (mrr_bridge.png,
    churn_customers_vs_revenue.png) — passed through unchanged, this
    module does not generate any chart of its own.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from pragmas_sdk.analysis.base import package_result
from pragmas_sdk.analysis.saas_metrics import run_saas_metrics

MODULE = "board_report"
REQUIRED_COLS = ["customer_id", "month", "mrr"]
KNOWN_PARAMS = frozenset({"cac", "gross_margin", "ebitda_margin_pct"})


def run_board_report(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    inner = run_saas_metrics(input_csv, params, output_dir)
    if not inner["success"]:
        return package_result(MODULE, output_dir, error=inner["error"])

    inner_results = inner["results"]
    months = inner_results["months"]
    last_month = months[-1]
    ending_mrr = inner_results["mrr_bridge"][last_month]["ending_mrr"]
    last_churn = inner_results["churn"][last_month]

    results = {
        "revenue": {
            "ending_mrr": ending_mrr,
            "arr": ending_mrr * 12,
        },
        "growth": {
            "annualized_mrr_growth_pct": inner_results["annualized_mrr_growth_pct"],
        },
        "churn": {
            "customer_churn_pct": last_churn["customer_churn_pct"],
            "revenue_churn_pct": last_churn["revenue_churn_pct"],
        },
        "rule_of_40": inner_results["rule_of_40"],
        "unit_economics": {
            "arpa": inner_results["arpa"],
            "cac": inner_results["cac"],
            "cac_payback_months": inner_results["cac_payback_months"],
            "ltv": inner_results["ltv"],
            "ltv_cac_ratio": inner_results["ltv_cac_ratio"],
        },
        "details": inner_results,
    }
    return package_result(MODULE, output_dir, results=results, charts=inner["charts"])
