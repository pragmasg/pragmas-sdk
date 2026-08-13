"""
Parametrized, tested analysis templates — run entirely on your machine,
no network call, no PRAGMAS account required.

Contract for every template:
    input  = CSV + params dict
    output = JSON-serializable dict {"success", "module", "results",
             "charts": [file paths], "error"} — results.json and charts
             are also written to output_dir.

Python templates (pandas/numpy/matplotlib):
    ecommerce_unit_economics — contribution margin by product/channel,
        CAC and break-even ROAS by channel, monthly-cohort LTV.
    saas_metrics — MRR bridge, customer vs revenue churn, CAC payback,
        LTV/CAC, Rule of 40.
    cash_flow_13w — 13-week cash flow projection.
    board_report — curated board-ready summary view over saas_metrics
        (same input, same params, no new math).

R templates (Rscript subprocess, ONLY fixed whitelisted templates — never
arbitrary code, same philosophy as the Python ones):
    r:seasonality, r:outliers, r:correlations — see r_runner.py. Require
    Rscript installed locally; everything else in this package doesn't.
"""

from pragmas_sdk.analysis.board_report import run_board_report
from pragmas_sdk.analysis.ecommerce_unit_economics import run_ecommerce_unit_economics
from pragmas_sdk.analysis.saas_metrics import run_saas_metrics
from pragmas_sdk.analysis.cash_flow_13w import run_cash_flow_13w
from pragmas_sdk.analysis.r_runner import run_r_analysis, R_TEMPLATES, r_available

MODULES = {
    "ecommerce_unit_economics": run_ecommerce_unit_economics,
    "saas_metrics": run_saas_metrics,
    "cash_flow_13w": run_cash_flow_13w,
    "board_report": run_board_report,
}


def list_modules() -> list:
    """All runnable template names (Python + R templates)."""
    return sorted(MODULES) + [f"r:{name}" for name in sorted(R_TEMPLATES)]


def run_module(name: str, input_csv, params: dict, output_dir) -> dict:
    """
    Dispatch by template name. R templates use the "r:<template>" prefix.
    Unknown names return a structured error (never raise) so callers can
    surface the message directly.
    """
    if name.startswith("r:"):
        return run_r_analysis(name[2:], input_csv, params, output_dir)
    fn = MODULES.get(name)
    if not fn:
        return {
            "success": False,
            "module": name,
            "results": {},
            "charts": [],
            "error": f"Unknown module: {name!r}. Available: {', '.join(list_modules())}",
        }
    return fn(input_csv, params, output_dir)


__all__ = [
    "MODULES",
    "R_TEMPLATES",
    "list_modules",
    "run_module",
    "run_ecommerce_unit_economics",
    "run_saas_metrics",
    "run_cash_flow_13w",
    "run_board_report",
    "run_r_analysis",
    "r_available",
]
