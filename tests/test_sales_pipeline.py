import csv
import os

import pytest

from pragmas_sdk.analysis.sales_pipeline import run_sales_pipeline


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


HEADER = ["deal_id", "stage", "amount", "created_date", "close_date", "status"]

ROWS = [
    ["D1", "Qualification", 10000, "2026-01-01", "2026-01-10", "won"],
    ["D2", "Qualification", 20000, "2026-01-02", "2026-01-20", "won"],
    ["D3", "Qualification", 15000, "2026-01-03", "", "lost"],
    ["D4", "Proposal", 30000, "2026-01-04", "2026-01-25", "won"],
    ["D5", "Proposal", 12000, "2026-01-05", "", "lost"],
    ["D6", "Proposal", 18000, "2026-01-06", "", "open"],
    ["D7", "Negotiation", 25000, "2026-01-07", "", "open"],
    ["D8", "Negotiation", 22000, "2026-01-08", "2026-01-30", "won"],
    ["D9", "Closed", 40000, "2026-01-09", "", "lost"],
    ["D10", "Qualification", 9000, "2026-01-10", "", "open"],
]


@pytest.fixture
def pipeline_csv(tmp_path):
    return _write_csv(tmp_path / "pipeline.csv", HEADER, ROWS)


# ── success case: hand-computed values ──────────────────────────────────


def test_success_hand_computed_values(pipeline_csv, tmp_path):
    result = run_sales_pipeline(str(pipeline_csv), {}, str(tmp_path / "out"))
    assert result["success"] is True, result["error"]
    r = result["results"]

    # win_rate = won / (won + lost) = 4 / 7
    assert r["win_rate"] == pytest.approx(4 / 7, abs=1e-3)
    assert r["won_deals"] == 4
    assert r["lost_deals"] == 3
    assert r["open_deals"] == 3

    # avg_deal_size = mean(amount) of won deals = (10000+20000+30000+22000)/4
    assert r["avg_deal_size"] == pytest.approx(20500.0)

    # open_pipeline_value = sum(amount) of open deals = 18000+25000+9000
    assert r["open_pipeline_value"] == pytest.approx(52000.0)

    # sales_cycle_days = mean of (close_date - created_date).days for won deals
    # deltas: 9, 18, 21, 22 -> mean 17.5
    assert r["sales_cycle_days"] == pytest.approx(17.5)

    # sales_velocity = decided * win_rate * avg_deal_size / sales_cycle_days
    #                = 7 * (4/7) * 20500 / 17.5 = 82000 / 17.5
    assert r["sales_velocity"] == pytest.approx(82000 / 17.5)

    assert r["stage_order"] == ["Qualification", "Proposal", "Negotiation", "Closed"]


def test_stage_conversion_snapshot_funnel(pipeline_csv, tmp_path):
    result = run_sales_pipeline(str(pipeline_csv), {}, str(tmp_path / "out"))
    r = result["results"]
    conv = r["stage_conversion"]
    # at-or-past counts: Qualification=10, Proposal=6, Negotiation=3, Closed=1
    assert conv["Qualification -> Proposal"] == pytest.approx(60.0)
    assert conv["Proposal -> Negotiation"] == pytest.approx(50.0)
    assert conv["Negotiation -> Closed"] == pytest.approx(100 / 3, abs=1e-3)


def test_forecast_per_stage(pipeline_csv, tmp_path):
    result = run_sales_pipeline(str(pipeline_csv), {}, str(tmp_path / "out"))
    r = result["results"]
    fc = r["forecast"]

    assert fc["Qualification"]["open_amount"] == pytest.approx(9000.0)
    assert fc["Qualification"]["win_rate_used"] == pytest.approx(4 / 7, abs=1e-3)
    assert fc["Qualification"]["method"] == "per_stage"
    assert fc["Qualification"]["forecast_amount"] == pytest.approx(9000 * 4 / 7, abs=1e-2)

    assert fc["Proposal"]["open_amount"] == pytest.approx(18000.0)
    assert fc["Proposal"]["win_rate_used"] == pytest.approx(0.5)
    assert fc["Proposal"]["forecast_amount"] == pytest.approx(9000.0)

    assert fc["Negotiation"]["open_amount"] == pytest.approx(25000.0)
    assert fc["Negotiation"]["win_rate_used"] == pytest.approx(0.5)
    assert fc["Negotiation"]["forecast_amount"] == pytest.approx(12500.0)

    assert fc["Closed"]["open_amount"] == pytest.approx(0.0)
    assert fc["Closed"]["win_rate_used"] == pytest.approx(0.0)


# ── quota / pipeline_coverage ────────────────────────────────────────────


def test_quota_given_computes_pipeline_coverage(pipeline_csv, tmp_path):
    result = run_sales_pipeline(str(pipeline_csv), {"quota": 50000}, str(tmp_path / "out"))
    r = result["results"]
    # 52000 / 50000 = 1.04
    assert r["pipeline_coverage"] == pytest.approx(1.04)
    assert r["open_pipeline_value"] == pytest.approx(52000.0)


def test_quota_absent_coverage_is_null(pipeline_csv, tmp_path):
    result = run_sales_pipeline(str(pipeline_csv), {}, str(tmp_path / "out"))
    r = result["results"]
    assert r["pipeline_coverage"] is None
    # open_pipeline_value is still reported
    assert r["open_pipeline_value"] == pytest.approx(52000.0)


# ── stage_order given vs inferred ────────────────────────────────────────


def test_stage_order_inferred_from_csv(pipeline_csv, tmp_path):
    result = run_sales_pipeline(str(pipeline_csv), {}, str(tmp_path / "out"))
    assert result["results"]["stage_order"] == ["Qualification", "Proposal", "Negotiation", "Closed"]


def test_stage_order_explicit_param_overrides_csv_order(pipeline_csv, tmp_path):
    explicit = ["Negotiation", "Proposal", "Qualification", "Closed"]
    result = run_sales_pipeline(
        str(pipeline_csv), {"stage_order": explicit}, str(tmp_path / "out")
    )
    r = result["results"]
    assert r["stage_order"] == explicit
    # with this order, at-or-past counts change: rank(Negotiation)=0 rank(Proposal)=1
    # rank(Qualification)=2 rank(Closed)=3
    # at_or_past[0] (rank>=0) = all 10 deals
    # at_or_past[1] (rank>=1) = Proposal, Qualification, Closed deals = 3(Proposal)+4(Qual)+1(Closed)=8
    conv = r["stage_conversion"]
    assert conv["Negotiation -> Proposal"] == pytest.approx(8 / 10 * 100, abs=1e-3)


# ── chart file exists and is non-empty ───────────────────────────────────


def test_chart_file_exists_and_nonempty(pipeline_csv, tmp_path):
    out_dir = tmp_path / "out"
    result = run_sales_pipeline(str(pipeline_csv), {}, str(out_dir))
    assert len(result["charts"]) == 1
    chart_path = result["charts"][0]
    assert os.path.isfile(chart_path)
    assert os.path.getsize(chart_path) > 0
    assert "pipeline_by_stage" in chart_path


# ── missing required column error ────────────────────────────────────────


def test_missing_required_column_returns_structured_error(tmp_path):
    path = _write_csv(
        tmp_path / "bad.csv",
        ["stage", "amount", "created_date", "close_date", "status"],  # no deal_id
        [["Qualification", 1000, "2026-01-01", "2026-01-05", "won"]],
    )
    result = run_sales_pipeline(str(path), {}, str(tmp_path / "out"))
    assert result["success"] is False
    assert "deal_id" in result["error"]


def test_missing_close_date_column_entirely_returns_clear_error(tmp_path):
    path = _write_csv(
        tmp_path / "no_close_date.csv",
        ["deal_id", "stage", "amount", "created_date", "status"],  # no close_date col
        [["D1", "Qualification", 1000, "2026-01-01", "won"]],
    )
    result = run_sales_pipeline(str(path), {}, str(tmp_path / "out"))
    assert result["success"] is False
    assert "close_date" in result["error"]


def test_invalid_status_value_returns_structured_error(tmp_path):
    path = _write_csv(
        tmp_path / "bad_status.csv",
        HEADER,
        [["D1", "Qualification", 1000, "2026-01-01", "", "pending"]],
    )
    result = run_sales_pipeline(str(path), {}, str(tmp_path / "out"))
    assert result["success"] is False
    assert "status" in result["error"]
