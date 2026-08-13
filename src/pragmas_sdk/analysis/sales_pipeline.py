"""
Sales pipeline analysis (CRM deals).

Input (CSV of deals), required columns:
    deal_id, stage, amount, created_date, status
Also expected as a column (validated separately, see below):
    close_date  — blank/empty for deals that are still open
Optional: owner

`close_date` is intentionally NOT in the required-columns check performed
by `load_csv`: a still-open deal legitimately has a blank `close_date`
value. What IS required is that the *column itself* exists in the CSV —
if the column is missing entirely we raise a clearer, dedicated error
rather than the generic "missing required columns" message, so a caller
can tell "you forgot the column" apart from "some rows aren't closed yet".

`status` must be one of `open`, `won`, `lost` (case-insensitive).

Params:
    quota:       optional revenue target (currency). When given,
                 `pipeline_coverage` = open_pipeline_value / quota. When
                 omitted (None), `pipeline_coverage` is reported as null —
                 `open_pipeline_value` itself is always reported either way.
    stage_order: optional list of stage names, earliest to latest. When
                 omitted, the order is inferred from the CSV: each stage's
                 rank is its order of first appearance scanning top to
                 bottom of the input file.

Output (results):
    win_rate: won / (won + lost), float 0-1. Deals with status == 'open'
        are excluded from both the numerator and denominator.
    avg_deal_size: mean `amount` of `won` deals only.
    open_pipeline_value: sum of `amount` for deals with status == 'open'.
        Always reported, independent of whether `quota` was given.
    pipeline_coverage: open_pipeline_value / quota if `quota` param was
        given, else null.
    sales_velocity: (decided_opportunities * win_rate * avg_deal_size) /
        avg_sales_cycle_days, the standard sales-velocity formula.
        `decided_opportunities` = count of deals with status in
        (won, lost) in the observed data — i.e. deals that have reached a
        decision. Deals still open are NOT counted here. Null if
        avg_sales_cycle_days is 0/undefined (no won deals) or there are no
        decided opportunities.
    stage_conversion: for each pair of adjacent stages (N, N+1) in
        `stage_order`, the % of deals currently AT-OR-PAST stage N that are
        also AT-OR-PAST stage N+1. IMPORTANT LIMITATION: the input only has
        each deal's *current* stage, not a historical stage-by-stage log,
        so this is a snapshot funnel over currently-observed stages, not a
        true historical conversion-over-time funnel. Documented here so it
        isn't overclaimed as the latter.
    sales_cycle_days: mean of (close_date - created_date).days for `won`
        deals only.
    forecast: per stage, sum(amount of open deals in that stage) *
        win_rate_applicable_from_that_stage_onward. Per-stage win rates are
        computed as won / (won + lost) among decided deals that are
        currently at-or-past that stage. If a stage has no decided deals to
        compute a per-stage rate from (too small/sparse data), the overall
        `win_rate` is used for that stage instead as a fallback — this
        fallback is applied per-stage as needed, not globally for the
        whole dataset.
Chart: bar chart of open pipeline value by stage.
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

MODULE = "sales_pipeline"
REQUIRED_COLS = ["deal_id", "stage", "amount", "created_date", "status"]
KNOWN_PARAMS = frozenset({"quota", "stage_order"})


def run_sales_pipeline(input_csv, params: Dict[str, Any], output_dir) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    params = params or {}
    try:
        df = load_csv(input_csv, REQUIRED_COLS, parse_dates=["created_date"])

        if "close_date" not in df.columns:
            raise AnalysisInputError(
                "Missing required column in CSV: close_date (may be blank for "
                "still-open deals, but the column itself must be present)"
            )
        df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce")

        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        if df["amount"].isna().any():
            raise AnalysisInputError("Column 'amount' contains non-numeric values")

        df["status"] = df["status"].astype(str).str.strip().str.lower()
        invalid_status = sorted(set(df["status"]) - {"open", "won", "lost"})
        if invalid_status:
            raise AnalysisInputError(
                f"Column 'status' contains values other than open/won/lost: {', '.join(invalid_status)}"
            )

        df["stage"] = df["stage"].astype(str)

        stage_order = params.get("stage_order")
        if stage_order:
            stage_order = [str(s) for s in stage_order]
        else:
            stage_order = list(dict.fromkeys(df["stage"].tolist()))

        won = df[df["status"] == "won"]
        lost = df[df["status"] == "lost"]
        open_deals = df[df["status"] == "open"]

        n_won = int(len(won))
        n_lost = int(len(lost))
        decided = n_won + n_lost
        win_rate = (n_won / decided) if decided else None

        avg_deal_size = float(won["amount"].mean()) if n_won else None

        open_pipeline_value = float(open_deals["amount"].sum())
        quota = params.get("quota")
        pipeline_coverage = (
            (open_pipeline_value / float(quota)) if quota not in (None, 0) else None
        )

        # sales_cycle_days: mean (close_date - created_date).days for won deals
        won_cycle = won.dropna(subset=["close_date", "created_date"])
        if len(won_cycle):
            cycle_days = (won_cycle["close_date"] - won_cycle["created_date"]).dt.days
            sales_cycle_days = float(cycle_days.mean())
        else:
            sales_cycle_days = None

        # sales_velocity: standard formula
        if (
            win_rate is not None
            and avg_deal_size is not None
            and sales_cycle_days
            and decided
        ):
            sales_velocity = (decided * win_rate * avg_deal_size) / sales_cycle_days
        else:
            sales_velocity = None

        # stage_conversion: snapshot funnel — deals currently AT-OR-PAST each stage
        stage_rank = {s: i for i, s in enumerate(stage_order)}
        df["_stage_rank"] = df["stage"].map(stage_rank)
        known = df.dropna(subset=["_stage_rank"])
        at_or_past_counts = [int((known["_stage_rank"] >= i).sum()) for i in range(len(stage_order))]

        stage_conversion: Dict[str, Any] = {}
        for i in range(len(stage_order) - 1):
            frm, to = stage_order[i], stage_order[i + 1]
            base = at_or_past_counts[i]
            nxt = at_or_past_counts[i + 1]
            stage_conversion[f"{frm} -> {to}"] = (nxt / base * 100) if base else None

        # forecast: per-stage win rate applied to open pipeline in that stage,
        # falling back to overall win_rate when a stage has no decided deals
        # at-or-past it.
        decided_known = known[known["status"].isin(["won", "lost"])]
        forecast: Dict[str, Any] = {}
        for i, stage in enumerate(stage_order):
            open_in_stage = open_deals[open_deals["stage"] == stage]
            open_amount = float(open_in_stage["amount"].sum())
            at_or_past = decided_known[decided_known["_stage_rank"] >= i]
            n_at_or_past_won = int((at_or_past["status"] == "won").sum())
            n_at_or_past_decided = len(at_or_past)
            if n_at_or_past_decided:
                stage_win_rate = n_at_or_past_won / n_at_or_past_decided
                method = "per_stage"
            else:
                stage_win_rate = win_rate if win_rate is not None else 0.0
                method = "fallback_overall_win_rate"
            forecast[stage] = {
                "open_amount": open_amount,
                "win_rate_used": stage_win_rate,
                "method": method,
                "forecast_amount": open_amount * stage_win_rate,
            }

        charts = []
        import matplotlib.pyplot as plt

        open_by_stage = {
            stage: float(open_deals.loc[open_deals["stage"] == stage, "amount"].sum())
            for stage in stage_order
        }
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.bar(list(open_by_stage), list(open_by_stage.values()), color="#1F3A5F")
        ax.set_title("Open pipeline value by stage")
        ax.set_ylabel("Open pipeline value")
        ax.tick_params(axis="x", rotation=45)
        charts.append(save_chart(fig, output_dir, "pipeline_by_stage"))

        results = {
            "win_rate": win_rate,
            "avg_deal_size": avg_deal_size,
            "open_pipeline_value": open_pipeline_value,
            "pipeline_coverage": pipeline_coverage,
            "sales_velocity": sales_velocity,
            "stage_conversion": stage_conversion,
            "sales_cycle_days": sales_cycle_days,
            "forecast": forecast,
            "stage_order": stage_order,
            "won_deals": n_won,
            "lost_deals": n_lost,
            "open_deals": int(len(open_deals)),
        }
        return package_result(MODULE, output_dir, results, charts)

    except AnalysisInputError as exc:
        return package_result(MODULE, output_dir, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — module must never raise to the caller
        return package_result(MODULE, output_dir, error=f"Unexpected error: {exc}")
