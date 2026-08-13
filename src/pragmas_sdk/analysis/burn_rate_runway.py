"""
Burn rate & runway analysis with scenario projection.

Input (CSV of monthly financials), required columns:
    month (YYYY-MM), revenue, opex
Optional:
    cash_balance — actual cash balance at the end of each month. When
        present it is treated as ground truth and its last value is used
        as `current_cash`. When absent, `current_cash` is derived as
        `starting_cash + cumulative_net(revenue - opex)` across every
        month in the CSV.

Params:
    starting_cash:            starting cash balance. Required ONLY if the
        CSV has no `cash_balance` column — if both are missing, raises
        AnalysisInputError("Provide either a cash_balance column or a
        starting_cash param").
    projection_months:        how many months forward to project the
        scenarios (default 12).
    optimistic_growth_pct / pessimistic_growth_pct: monthly revenue growth
        rate (%) to use for the optimistic/pessimistic scenarios. If not
        given, derived from the observed historical month-over-month
        revenue growth trend:
            - with >= 2 months of usable data, base_growth_pct is the
              average observed MoM revenue growth (%), and the default
              optimistic/pessimistic rates are base_growth_pct plus/minus
              half of abs(base_growth_pct);
            - with < 2 months of usable data (no trend can be computed),
              base_growth_pct is treated as 0 and the default
              optimistic/pessimistic rates are +20 / -20 percentage
              points.
    Simplifying assumption for every scenario: opex stays flat at its
    last observed value for the whole projection window; only revenue
    grows (or shrinks) at the scenario's monthly rate.

Output (results):
    monthly_burn:      list of {month, burn} — burn = opex - revenue for
        each historical month (positive = burning cash that month).
    avg_burn:           mean of the historical monthly burn values.
    current_cash:       latest known/derived cash balance (see above).
    runway_months:      current_cash / avg_burn, or null if avg_burn <= 0
        (business is cash-flow positive on average — runway doesn't
        apply).
    runway_note:        human-readable explanation of runway_months,
        especially when it is null.
    base_growth_pct:    observed average historical MoM revenue growth
        (%), used as the base-case scenario growth rate.
    optimistic_growth_pct / pessimistic_growth_pct: the monthly growth
        rates (%) actually used for those scenarios (given or derived,
        see Params above).
    projection_months:  number of months projected forward.
    scenarios:          {base, optimistic, pessimistic} — each a list of
        {month, revenue, opex, net, cash_balance} for every projected
        month, opex held flat per the assumption above.
Chart: historical cash balance (actual or derived) + the three projected
    scenario lines forward from the last historical point.
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

MODULE = "burn_rate_runway"
REQUIRED_COLS = ["month", "revenue", "opex"]
KNOWN_PARAMS = frozenset(
    {"starting_cash", "projection_months", "optimistic_growth_pct", "pessimistic_growth_pct"}
)
TREND_FALLBACK_PP = 20.0  # ± percentage points when a growth trend can't be computed


def run_burn_rate_runway(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    params = params or {}
    try:
        df = load_csv(input_csv, REQUIRED_COLS)
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
        df["opex"] = pd.to_numeric(df["opex"], errors="coerce")
        if df["revenue"].isna().any():
            raise AnalysisInputError("Column 'revenue' contains non-numeric values")
        if df["opex"].isna().any():
            raise AnalysisInputError("Column 'opex' contains non-numeric values")
        try:
            df["month"] = pd.PeriodIndex(df["month"].astype(str), freq="M")
        except Exception as exc:
            raise AnalysisInputError(f"Invalid month format (expected YYYY-MM): {exc}") from exc

        df = df.sort_values("month").reset_index(drop=True)
        has_cash_col = "cash_balance" in df.columns

        if has_cash_col:
            df["cash_balance"] = pd.to_numeric(df["cash_balance"], errors="coerce")
            if df["cash_balance"].isna().any():
                raise AnalysisInputError("Column 'cash_balance' contains non-numeric values")
            historical_cash = df["cash_balance"].astype(float).tolist()
        else:
            starting_cash = params.get("starting_cash")
            if starting_cash is None:
                raise AnalysisInputError(
                    "Provide either a cash_balance column or a starting_cash param"
                )
            starting_cash = float(starting_cash)
            cumulative_net = (df["revenue"] - df["opex"]).cumsum()
            historical_cash = (starting_cash + cumulative_net).astype(float).tolist()

        current_cash = float(historical_cash[-1])

        burns = (df["opex"] - df["revenue"]).astype(float)
        monthly_burn = [
            {"month": str(m), "burn": float(b)} for m, b in zip(df["month"], burns)
        ]
        avg_burn = float(burns.mean())

        if avg_burn > 0:
            runway_months = current_cash / avg_burn
            runway_note = (
                f"~{runway_months:.1f} months of runway at the current average burn rate."
            )
        else:
            runway_months = None
            runway_note = (
                "Runway is not applicable: the business is cash-flow positive on average "
                "(avg_burn <= 0)."
            )

        # Base-case growth rate: observed average month-over-month revenue growth.
        revenues = df["revenue"].astype(float).tolist()
        growth_rates = [
            (revenues[i] / revenues[i - 1] - 1)
            for i in range(1, len(revenues))
            if revenues[i - 1] != 0
        ]
        if growth_rates:
            base_growth_pct = float(sum(growth_rates) / len(growth_rates) * 100)
            adjustment_pp = abs(base_growth_pct) / 2
        else:
            base_growth_pct = 0.0
            adjustment_pp = TREND_FALLBACK_PP

        optimistic_growth_pct = float(
            params.get("optimistic_growth_pct", base_growth_pct + adjustment_pp)
        )
        pessimistic_growth_pct = float(
            params.get("pessimistic_growth_pct", base_growth_pct - adjustment_pp)
        )

        projection_months = int(params.get("projection_months", 12))
        if projection_months <= 0:
            raise AnalysisInputError("projection_months must be a positive integer")

        last_month = df["month"].iloc[-1]
        last_revenue = float(revenues[-1])
        flat_opex = float(df["opex"].iloc[-1])

        def _project(growth_pct: float):
            rate = growth_pct / 100
            series = []
            cash = current_cash
            for i in range(1, projection_months + 1):
                month = last_month + i
                revenue = last_revenue * ((1 + rate) ** i)
                net = revenue - flat_opex
                cash += net
                series.append({
                    "month": str(month),
                    "revenue": float(revenue),
                    "opex": flat_opex,
                    "net": float(net),
                    "cash_balance": float(cash),
                })
            return series

        scenarios = {
            "base": _project(base_growth_pct),
            "optimistic": _project(optimistic_growth_pct),
            "pessimistic": _project(pessimistic_growth_pct),
        }

        charts = []
        import matplotlib.pyplot as plt

        hist_labels = [str(m) for m in df["month"]]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(hist_labels, historical_cash, color="#1F3A5F", marker="o", label="Historical cash")

        colors = {"base": "#2E7D32", "optimistic": "#81C784", "pessimistic": "#C62828"}
        last_label = hist_labels[-1]
        for name, series in scenarios.items():
            labels = [last_label] + [row["month"] for row in series]
            values = [current_cash] + [row["cash_balance"] for row in series]
            ax.plot(labels, values, color=colors[name], marker="s", linestyle="--",
                     label=f"{name.capitalize()} scenario")

        ax.axhline(0, color="black", linewidth=0.8, linestyle=":")
        ax.set_title("Cash balance — historical + projected scenarios")
        ax.set_ylabel("Cash balance")
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.legend(fontsize=8)
        charts.append(save_chart(fig, output_dir, "cash_runway"))

        results = {
            "monthly_burn": monthly_burn,
            "avg_burn": avg_burn,
            "current_cash": current_cash,
            "runway_months": runway_months,
            "runway_note": runway_note,
            "base_growth_pct": base_growth_pct,
            "optimistic_growth_pct": optimistic_growth_pct,
            "pessimistic_growth_pct": pessimistic_growth_pct,
            "projection_months": projection_months,
            "scenarios": scenarios,
        }
        return package_result(MODULE, output_dir, results, charts)

    except AnalysisInputError as exc:
        return package_result(MODULE, output_dir, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return package_result(MODULE, output_dir, error=f"Unexpected error: {exc}")
