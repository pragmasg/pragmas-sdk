"""
13-week cash flow projection.

Input (CSV of projected movements), required columns:
    date, concept, amount   (amount: positive = inflow, negative = outflow)
Optional: category

Params:
    opening_balance: starting cash balance (default 0)
    start_date:      projection start date, YYYY-MM-DD
                     (default: Monday of the first movement's week)

Output (results):
    weeks: per week — week_start, inflows, outflows, net, closing_balance
    min_balance / min_balance_week, weeks_negative,
    total_inflows / total_outflows / net_13w
Chart: weekly balance (line) + weekly net (bars).
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

MODULE = "cash_flow_13w"
REQUIRED_COLS = ["date", "concept", "amount"]
N_WEEKS = 13


def run_cash_flow_13w(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    params = params or {}
    try:
        df = load_csv(input_csv, REQUIRED_COLS, parse_dates=["date"])
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        if df["amount"].isna().any():
            raise AnalysisInputError("Column 'amount' contains non-numeric values")

        opening_balance = float(params.get("opening_balance", 0.0))
        start_raw = params.get("start_date")
        if start_raw:
            start = pd.Timestamp(start_raw)
        else:
            start = df["date"].min()
        start = (start - pd.Timedelta(days=int(start.dayofweek))).normalize()  # Monday
        end = start + pd.Timedelta(weeks=N_WEEKS)

        window = df[(df["date"] >= start) & (df["date"] < end)].copy()
        window["week_index"] = ((window["date"] - start).dt.days // 7).astype(int)

        weeks = []
        balance = opening_balance
        for i in range(N_WEEKS):
            wk = window[window["week_index"] == i]
            inflows = float(wk.loc[wk["amount"] > 0, "amount"].sum())
            outflows = float(wk.loc[wk["amount"] < 0, "amount"].sum())
            net = inflows + outflows
            balance += net
            weeks.append({
                "week": i + 1,
                "week_start": str((start + pd.Timedelta(weeks=i)).date()),
                "inflows": inflows,
                "outflows": outflows,
                "net": net,
                "closing_balance": balance,
            })

        min_week = min(weeks, key=lambda w: w["closing_balance"])
        ignored = int(len(df) - len(window))

        charts = []
        import matplotlib.pyplot as plt

        labels = [w["week_start"] for w in weeks]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(labels, [w["net"] for w in weeks], color="#81C784", label="Weekly net")
        ax.plot(labels, [w["closing_balance"] for w in weeks],
                color="#1F3A5F", marker="o", label="Cash balance")
        ax.axhline(0, color="#C62828", linewidth=0.8, linestyle="--")
        ax.set_title(f"Cash flow — {N_WEEKS}-week projection")
        ax.set_ylabel("Amount")
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.legend(fontsize=8)
        charts.append(save_chart(fig, output_dir, "cash_flow_13w"))

        results = {
            "start_date": str(start.date()),
            "opening_balance": opening_balance,
            "weeks": weeks,
            "min_balance": min_week["closing_balance"],
            "min_balance_week": min_week["week_start"],
            "weeks_negative": sum(1 for w in weeks if w["closing_balance"] < 0),
            "total_inflows": sum(w["inflows"] for w in weeks),
            "total_outflows": sum(w["outflows"] for w in weeks),
            "net_13w": sum(w["net"] for w in weeks),
            "movements_outside_window": ignored,
        }
        return package_result(MODULE, output_dir, results, charts)

    except AnalysisInputError as exc:
        return package_result(MODULE, output_dir, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return package_result(MODULE, output_dir, error=f"Unexpected error: {exc}")
