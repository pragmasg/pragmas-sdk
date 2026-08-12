"""Shared helpers for analysis modules: CSV loading with validation,
chart saving (matplotlib Agg), result packaging.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import matplotlib

matplotlib.use("Agg")  # headless: never require a display server

import pandas as pd

logger = logging.getLogger("pragmas_sdk.analysis")


class AnalysisInputError(ValueError):
    """Bad input CSV / params — message is safe to show to the user."""


def load_csv(
    input_csv,
    required_cols: Iterable[str],
    parse_dates: Optional[List[str]] = None,
) -> pd.DataFrame:
    path = Path(input_csv)
    if not path.is_file():
        raise AnalysisInputError(f"Input CSV not found: {path}")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise AnalysisInputError(f"Could not read CSV: {exc}") from exc
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise AnalysisInputError(
            f"Missing required columns in CSV: {', '.join(missing)}. "
            f"Columns present: {', '.join(df.columns)}"
        )
    if df.empty:
        raise AnalysisInputError("Input CSV is empty")
    for col in parse_dates or []:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        if df[col].isna().all():
            raise AnalysisInputError(f"Column '{col}' does not contain valid dates")
    return df


def save_chart(fig, output_dir: Path, name: str) -> str:
    """Save a matplotlib figure as PNG and close it. Returns the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    import matplotlib.pyplot as plt

    plt.close(fig)
    return str(path)


def _round_floats(obj: Any, ndigits: int = 4) -> Any:
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def package_result(
    module: str,
    output_dir,
    results: Optional[Dict[str, Any]] = None,
    charts: Optional[List[str]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the standard result dict; on success also persist results.json
    next to the charts so downstream tooling can pick everything up.
    """
    out = {
        "success": error is None,
        "module": module,
        "results": _round_floats(results or {}),
        "charts": charts or [],
        "error": error,
    }
    if error is None:
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "results.json").write_text(
                json.dumps(out["results"], ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Could not write results.json: %s", exc)
    return out
