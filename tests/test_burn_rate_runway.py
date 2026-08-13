import csv
from pathlib import Path

from pragmas_sdk.analysis import run_module


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def test_burn_rate_runway_with_cash_balance_column(tmp_path):
    rows = [
        ["2026-01", 10000, 15000, 90000],
        ["2026-02", 11000, 15500, 85500],
        ["2026-03", 12000, 16000, 81500],
    ]
    csv_path = _write_csv(
        tmp_path / "burn.csv", ["month", "revenue", "opex", "cash_balance"], rows
    )
    result = run_module(
        "burn_rate_runway", str(csv_path), {"projection_months": 3}, tmp_path / "out"
    )
    assert result["success"] is True, result["error"]
    results = result["results"]

    burns = [15000 - 10000, 15500 - 11000, 16000 - 12000]  # 5000, 4500, 4000
    expected_avg_burn = sum(burns) / len(burns)
    assert results["avg_burn"] == expected_avg_burn
    assert results["current_cash"] == 81500.0
    assert results["runway_months"] == round(81500.0 / expected_avg_burn, 4)
    assert len(results["monthly_burn"]) == 3
    assert results["monthly_burn"][0] == {"month": "2026-01", "burn": 5000.0}
    for scenario in ("base", "optimistic", "pessimistic"):
        assert len(results["scenarios"][scenario]) == 3


def test_burn_rate_runway_without_cash_balance_uses_starting_cash(tmp_path):
    rows = [
        ["2026-01", 10000, 15000],
        ["2026-02", 11000, 15500],
        ["2026-03", 12000, 16000],
    ]
    csv_path = _write_csv(tmp_path / "burn.csv", ["month", "revenue", "opex"], rows)
    result = run_module(
        "burn_rate_runway",
        str(csv_path),
        {"starting_cash": 100000, "projection_months": 2},
        tmp_path / "out",
    )
    assert result["success"] is True, result["error"]
    results = result["results"]

    net_by_month = [10000 - 15000, 11000 - 15500, 12000 - 16000]  # -5000, -4500, -4000
    expected_cash = 100000 + sum(net_by_month)
    assert results["current_cash"] == expected_cash
    assert results["avg_burn"] == (5000 + 4500 + 4000) / 3


def test_burn_rate_runway_missing_cash_and_starting_cash_errors(tmp_path):
    rows = [
        ["2026-01", 10000, 15000],
        ["2026-02", 11000, 15500],
    ]
    csv_path = _write_csv(tmp_path / "burn.csv", ["month", "revenue", "opex"], rows)
    result = run_module("burn_rate_runway", str(csv_path), {}, tmp_path / "out")
    assert result["success"] is False
    assert "starting_cash" in result["error"]
    assert "cash_balance" in result["error"]


def test_burn_rate_runway_cash_flow_positive_has_null_runway(tmp_path):
    rows = [
        ["2026-01", 20000, 10000, 90000],
        ["2026-02", 21000, 10500, 100500],
        ["2026-03", 22000, 11000, 111500],
    ]
    csv_path = _write_csv(
        tmp_path / "burn.csv", ["month", "revenue", "opex", "cash_balance"], rows
    )
    result = run_module("burn_rate_runway", str(csv_path), {}, tmp_path / "out")
    assert result["success"] is True, result["error"]
    results = result["results"]
    assert results["avg_burn"] <= 0
    assert results["runway_months"] is None
    assert "not applicable" in results["runway_note"]


def test_burn_rate_runway_chart_file_is_non_empty(tmp_path):
    rows = [
        ["2026-01", 10000, 15000, 90000],
        ["2026-02", 11000, 15500, 85500],
        ["2026-03", 12000, 16000, 81500],
    ]
    csv_path = _write_csv(
        tmp_path / "burn.csv", ["month", "revenue", "opex", "cash_balance"], rows
    )
    out_dir = tmp_path / "out"
    result = run_module("burn_rate_runway", str(csv_path), {}, out_dir)
    assert result["success"] is True, result["error"]
    assert len(result["charts"]) == 1
    chart_path = Path(result["charts"][0])
    assert chart_path.is_file()
    assert chart_path.stat().st_size > 0
