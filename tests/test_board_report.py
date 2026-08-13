import csv

import pytest

from pragmas_sdk.analysis.board_report import run_board_report
from pragmas_sdk.analysis.saas_metrics import run_saas_metrics


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _saas_rows():
    # 3 customers, 3 months. A churns after month 1, B grows, C is new in
    # month 3 — enough variety to exercise new/expansion/contraction/churn.
    return [
        ["cust_a", "2026-01", 100],
        ["cust_b", "2026-01", 200],
        ["cust_b", "2026-02", 250],
        ["cust_b", "2026-03", 300],
        ["cust_c", "2026-03", 150],
    ]


@pytest.fixture
def saas_csv(tmp_path):
    return _write_csv(
        tmp_path / "saas.csv", ["customer_id", "month", "mrr"], _saas_rows()
    )


@pytest.fixture
def single_month_csv(tmp_path):
    rows = [["cust_a", "2026-01", 100], ["cust_b", "2026-01", 200]]
    return _write_csv(
        tmp_path / "single_month.csv", ["customer_id", "month", "mrr"], rows
    )


def test_board_report_success_with_cac(saas_csv, tmp_path):
    out_dir = tmp_path / "out"
    result = run_board_report(
        str(saas_csv), {"cac": 500, "gross_margin": 0.8}, str(out_dir)
    )
    assert result["success"] is True, result["error"]
    assert result["module"] == "board_report"

    results = result["results"]
    assert (
        results["revenue"]["arr"] == results["revenue"]["ending_mrr"] * 12
    )

    # details must match a direct run_saas_metrics call on the same input
    direct = run_saas_metrics(
        str(saas_csv), {"cac": 500, "gross_margin": 0.8}, str(tmp_path / "direct")
    )
    assert results["details"] == direct["results"]

    # curated fields are extracted/renamed correctly from the inner results
    last_month = direct["results"]["months"][-1]
    assert (
        results["revenue"]["ending_mrr"]
        == direct["results"]["mrr_bridge"][last_month]["ending_mrr"]
    )
    assert (
        results["growth"]["annualized_mrr_growth_pct"]
        == direct["results"]["annualized_mrr_growth_pct"]
    )
    assert (
        results["churn"]["customer_churn_pct"]
        == direct["results"]["churn"][last_month]["customer_churn_pct"]
    )
    assert (
        results["churn"]["revenue_churn_pct"]
        == direct["results"]["churn"][last_month]["revenue_churn_pct"]
    )
    assert results["rule_of_40"] == direct["results"]["rule_of_40"]
    assert results["unit_economics"] == {
        "arpa": direct["results"]["arpa"],
        "cac": direct["results"]["cac"],
        "cac_payback_months": direct["results"]["cac_payback_months"],
        "ltv": direct["results"]["ltv"],
        "ltv_cac_ratio": direct["results"]["ltv_cac_ratio"],
    }
    # cac was given, so CAC-dependent fields must be populated (not null)
    assert results["unit_economics"]["cac_payback_months"] is not None
    assert results["unit_economics"]["ltv_cac_ratio"] is not None


def test_board_report_charts_match_saas_metrics(saas_csv, tmp_path):
    out_dir = tmp_path / "out"
    result = run_board_report(str(saas_csv), {}, str(out_dir))
    assert result["success"] is True, result["error"]
    assert result["charts"] != []

    direct = run_saas_metrics(str(saas_csv), {}, str(tmp_path / "direct"))
    # same chart filenames (board_report reuses saas_metrics's own output_dir)
    assert [
        str(p).rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in result["charts"]
    ] == [
        str(p).rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in direct["charts"]
    ]


def test_board_report_without_cac_nulls_cac_fields(saas_csv, tmp_path):
    result = run_board_report(str(saas_csv), {}, str(tmp_path / "out"))
    assert result["success"] is True, result["error"]
    ue = result["results"]["unit_economics"]
    assert ue["cac"] is None
    assert ue["cac_payback_months"] is None
    assert ue["ltv_cac_ratio"] is None


def test_board_report_propagates_real_underlying_error(single_month_csv, tmp_path):
    result = run_board_report(str(single_month_csv), {}, str(tmp_path / "out"))
    assert result["success"] is False
    assert result["module"] == "board_report"
    assert "At least 2 months of data are required" in result["error"]
    assert result["results"] == {}
    assert result["charts"] == []
