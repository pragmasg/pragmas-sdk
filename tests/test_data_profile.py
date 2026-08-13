import csv
import os
from pathlib import Path

from pragmas_sdk import PragmasClient


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


# 10 data rows. Columns:
#   id       — sequential unique ints 1..10            -> id-like
#   date     — 5 distinct dates repeated twice each      -> date
#   status   — 3 distinct categorical values             -> categorical
#   amount   — numeric, 2 missing, some repeats           -> numeric
_HEADER = ["id", "date", "status", "amount"]
_ROWS = [
    [1, "2026-01-01", "active", "100"],
    [2, "2026-01-02", "active", "150"],
    [3, "2026-01-03", "pending", "150"],
    [4, "2026-01-04", "pending", ""],
    [5, "2026-01-05", "closed", "500"],
    [6, "2026-01-01", "active", "500"],
    [7, "2026-01-02", "active", ""],
    [8, "2026-01-03", "pending", "100"],
    [9, "2026-01-04", "pending", "9999"],
    [10, "2026-01-05", "closed", "120"],
]


def _client():
    return PragmasClient(base_url="https://api.pragmas.io")


def test_data_profile_success_with_missing_and_mixed_types(tmp_path):
    csv_path = _write_csv(tmp_path / "data.csv", _HEADER, _ROWS)
    client = _client()
    try:
        result = client.analyze(str(csv_path), "data_profile", output_dir=str(tmp_path / "out"))
    finally:
        client.close()

    assert result.success is True, result.error
    assert result.module == "data_profile"

    assert result.results["row_count"] == 10
    assert result.results["column_count"] == 4

    columns = result.results["columns"]
    assert set(columns) == set(_HEADER)

    # amount: 2 missing out of 10 rows
    assert columns["amount"]["missing_count"] == 2
    assert columns["amount"]["missing_pct"] == 20.0
    assert columns["amount"]["inferred_type"] == "numeric"

    # id: fully unique, no missing -> id-like
    assert columns["id"]["missing_count"] == 0
    assert columns["id"]["unique_count"] == 10
    assert columns["id"]["inferred_type"] == "id-like"
    assert "id" in result.results["potential_id_columns"]

    # date: only 5 distinct values across 10 rows -> not id-like, parses as date
    assert columns["date"]["unique_count"] == 5
    assert columns["date"]["inferred_type"] == "date"
    assert "date" in result.results["potential_date_columns"]

    # status: 3 distinct categorical values
    assert columns["status"]["unique_count"] == 3
    assert columns["status"]["inferred_type"] == "categorical"
    assert "status" in result.results["potential_categorical_columns"]

    assert result.results["duplicate_row_count"] == 0

    # Only one inferred-numeric column ("amount") -> no correlation matrix
    assert result.results["correlation_matrix"] == {}

    # IQR outliers computed for the numeric column
    assert "amount" in result.results["outliers"]
    assert isinstance(result.results["outliers"]["amount"], int)


def test_data_profile_missing_values_chart_exists_and_nonempty(tmp_path):
    csv_path = _write_csv(tmp_path / "data.csv", _HEADER, _ROWS)
    client = _client()
    try:
        result = client.analyze(str(csv_path), "data_profile", output_dir=str(tmp_path / "out"))
    finally:
        client.close()

    assert result.success is True, result.error
    assert len(result.charts) == 1
    chart_path = Path(result.charts[0])
    assert chart_path.is_file()
    assert os.path.getsize(chart_path) > 0
    assert chart_path.name == "missing_values.png"


def test_data_profile_zero_missing_values_succeeds_without_chart(tmp_path):
    rows_no_missing = [row for row in _ROWS if row[3] != ""]
    # backfill the two rows that had blank amounts so every row has a value
    rows_no_missing = [
        [1, "2026-01-01", "active", "100"],
        [2, "2026-01-02", "active", "150"],
        [3, "2026-01-03", "pending", "150"],
        [4, "2026-01-04", "pending", "300"],
        [5, "2026-01-05", "closed", "500"],
    ]
    csv_path = _write_csv(tmp_path / "clean.csv", _HEADER, rows_no_missing)
    client = _client()
    try:
        result = client.analyze(str(csv_path), "data_profile", output_dir=str(tmp_path / "out"))
    finally:
        client.close()

    assert result.success is True, result.error
    for info in result.results["columns"].values():
        assert info["missing_count"] == 0
    assert result.charts == []


def test_data_profile_missing_csv_returns_structured_error(tmp_path):
    client = _client()
    try:
        result = client.analyze(str(tmp_path / "nope.csv"), "data_profile")
    finally:
        client.close()

    assert result.success is False
    assert "not found" in result.error


def test_data_profile_empty_csv_returns_structured_error(tmp_path):
    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("", encoding="utf-8")
    client = _client()
    try:
        result = client.analyze(str(empty_path), "data_profile")
    finally:
        client.close()

    assert result.success is False
    assert result.error
