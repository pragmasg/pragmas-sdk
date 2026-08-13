import csv
import os

import pytest

from pragmas_sdk.analysis.cohort_analysis import run_cohort_analysis


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


@pytest.fixture
def cohort_csv(tmp_path):
    # Cohort 2026-01: customers c1, c2 — first activity Jan 2026.
    #   c1: Jan=100, Feb=50, Mar=25   (both active every month)
    #   c2: Jan=100, Feb=50           (churns before March — no March row)
    # Cohort 2026-02: customers c3, c4 — first activity Feb 2026.
    #   c3: Feb=200, Mar=200
    #   c4: Feb=200, Mar=0 (churns — has a $0 row, still counts as "active")
    rows = [
        ["c1", "2026-01-05", 100],
        ["c1", "2026-02-05", 50],
        ["c1", "2026-03-05", 25],
        ["c2", "2026-01-10", 100],
        ["c2", "2026-02-10", 50],
        ["c3", "2026-02-01", 200],
        ["c3", "2026-03-01", 200],
        ["c4", "2026-02-15", 200],
        ["c4", "2026-03-15", 0],
    ]
    return _write_csv(tmp_path / "cohort.csv", ["customer_id", "date", "revenue"], rows)


def test_success_hand_computed_retention(cohort_csv, tmp_path):
    result = run_cohort_analysis(str(cohort_csv), {}, tmp_path / "out")
    assert result["success"] is True, result["error"]
    assert result["module"] == "cohort_analysis"

    cohorts = result["results"]["cohorts"]
    assert set(result["results"]["cohort_months"]) == {"2026-01", "2026-02"}

    jan = cohorts["2026-01"]
    assert jan["customer_count"] == 2
    # month0: 100+100=200, month1: 50+50=100, month2: 25+0=25
    assert jan["revenue_by_month_index"][0] == 200.0
    assert jan["revenue_by_month_index"][1] == 100.0
    assert jan["revenue_by_month_index"][2] == 25.0
    # revenue retention: 100%, 100/200*100=50%, 25/200*100=12.5%
    assert jan["revenue_retention_pct"][0] == 100.0
    assert jan["revenue_retention_pct"][1] == 50.0
    assert jan["revenue_retention_pct"][2] == 12.5
    # customer retention: both active month0 & 1 (100%), only c1 in month2 (50%)
    assert jan["customer_retention_pct"][0] == 100.0
    assert jan["customer_retention_pct"][1] == 100.0
    assert jan["customer_retention_pct"][2] == 50.0

    feb = cohorts["2026-02"]
    assert feb["customer_count"] == 2
    # month0: 200+200=400, month1: 200+0=200
    assert feb["revenue_by_month_index"][0] == 400.0
    assert feb["revenue_by_month_index"][1] == 200.0
    assert feb["revenue_retention_pct"][0] == 100.0
    assert feb["revenue_retention_pct"][1] == 50.0
    # customer retention: c4 still has a row (revenue=0) in month1 -> both active
    assert feb["customer_retention_pct"][0] == 100.0
    assert feb["customer_retention_pct"][1] == 100.0


def test_horizon_months_truncates_output(cohort_csv, tmp_path):
    result = run_cohort_analysis(str(cohort_csv), {"horizon_months": 2}, tmp_path / "out")
    assert result["success"] is True, result["error"]
    assert result["results"]["horizon_months"] == 2
    for cohort in result["results"]["cohorts"].values():
        assert len(cohort["revenue_by_month_index"]) == 2
        assert len(cohort["revenue_retention_pct"]) == 2
        assert len(cohort["customer_retention_pct"]) == 2


def test_chart_file_exists_and_is_non_empty(cohort_csv, tmp_path):
    out_dir = tmp_path / "out"
    result = run_cohort_analysis(str(cohort_csv), {}, out_dir)
    assert result["success"] is True, result["error"]
    assert len(result["charts"]) == 1
    chart_path = result["charts"][0]
    assert os.path.isfile(chart_path)
    assert os.path.getsize(chart_path) > 0


def test_single_cohort_raises_clean_error(tmp_path):
    rows = [
        ["c1", "2026-01-05", 100],
        ["c2", "2026-01-10", 100],
    ]
    csv_path = _write_csv(tmp_path / "single_cohort.csv", ["customer_id", "date", "revenue"], rows)
    result = run_cohort_analysis(str(csv_path), {}, tmp_path / "out")
    assert result["success"] is False
    assert "At least 2 distinct cohort months" in result["error"]


def test_missing_required_column_raises_clean_error(tmp_path):
    rows = [
        ["c1", "2026-01-05"],
        ["c2", "2026-02-10"],
    ]
    csv_path = _write_csv(tmp_path / "missing_col.csv", ["customer_id", "date"], rows)
    result = run_cohort_analysis(str(csv_path), {}, tmp_path / "out")
    assert result["success"] is False
    assert "Missing required columns" in result["error"]
    assert "revenue" in result["error"]
