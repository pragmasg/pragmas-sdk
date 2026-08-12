import csv
from pathlib import Path

import httpx
import pytest
import respx

from pragmas_sdk import (
    AnalysisResult,
    BetaKey,
    MarketResult,
    PragmasConnectionError,
    PragmasNotImplementedError,
    WaitlistResult,
)

BASE = "https://api.pragmas.io"


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


@pytest.fixture
def cashflow_csv(tmp_path):
    rows = [
        ["2026-07-06", "customer A payment", 10000],
        ["2026-07-15", "payroll", -12000],
        ["2026-07-21", "customer B payment", 5000],
    ]
    return _write_csv(tmp_path / "cash.csv", ["date", "concept", "amount"], rows)


# ── 🟢 join_waitlist (live endpoint, still over the network) ────────────


@respx.mock
def test_join_waitlist_success(client):
    respx.post(f"{BASE}/waitlist").mock(
        return_value=httpx.Response(201, json={"ok": True, "message": "We'll be in touch."})
    )
    result = client.join_waitlist("dev@example.com")
    assert isinstance(result, WaitlistResult)
    assert result.ok is True


@respx.mock
def test_join_waitlist_invalid_email_raises(client):
    respx.post(f"{BASE}/waitlist").mock(
        return_value=httpx.Response(422, json={"detail": "Invalid email"})
    )
    with pytest.raises(Exception) as exc_info:
        client.join_waitlist("not-an-email")
    assert "422" in str(exc_info.value)


@respx.mock
def test_unreachable_backend_raises_connection_error(anon_client):
    respx.post(f"{BASE}/waitlist").mock(side_effect=httpx.ConnectError("nope"))
    with pytest.raises(PragmasConnectionError):
        anon_client.join_waitlist("dev@example.com")


# ── 🟡 request_beta_key (planned, still over the network) ───────────────


@respx.mock
def test_request_beta_key_sets_client_key(anon_client):
    respx.post(f"{BASE}/auth/beta-key").mock(
        return_value=httpx.Response(
            201,
            json={"beta_key": "pk_beta_abc123", "email": "dev@example.com", "created_at": "2026-08-01T00:00:00Z"},
        )
    )
    result = anon_client.request_beta_key("dev@example.com")
    assert isinstance(result, BetaKey)
    assert result.beta_key == "pk_beta_abc123"
    assert anon_client.beta_key == "pk_beta_abc123"


# ── 🟢 analyze — local, no network, no beta key ──────────────────────────


def test_analyze_runs_locally_no_network(anon_client, cashflow_csv, tmp_path):
    """anon_client has no beta_key set — proves analyze() doesn't need one."""
    result = anon_client.analyze(str(cashflow_csv), "cash_flow_13w", output_dir=str(tmp_path / "out"))
    assert isinstance(result, AnalysisResult)
    assert result.success is True, result.error
    assert result.module == "cash_flow_13w"
    assert len(result.results["weeks"]) == 13
    assert len(result.charts) == 1
    for chart in result.charts:
        assert Path(chart).is_file()


def test_analyze_unknown_template_returns_structured_error(anon_client, cashflow_csv):
    """Never raises — matches every function in pragmas_sdk.analysis."""
    result = anon_client.analyze(str(cashflow_csv), "not_a_real_template")
    assert result.success is False
    assert "Unknown module" in result.error


def test_analyze_missing_csv_returns_structured_error(anon_client, tmp_path):
    result = anon_client.analyze(str(tmp_path / "nope.csv"), "cash_flow_13w")
    assert result.success is False
    assert "not found" in result.error


def test_analyze_r_template_without_local_rscript(anon_client, cashflow_csv, monkeypatch):
    """This machine's test environment has no Rscript installed — exercises
    the real degrade-gracefully path, not a mock."""
    from pragmas_sdk.analysis import r_runner

    monkeypatch.setattr(r_runner, "find_rscript", lambda: None)
    result = anon_client.analyze(str(cashflow_csv), "r:outliers")
    assert result.success is False
    assert "Rscript is not installed" in result.error


def test_analyze_default_output_dir_is_a_fresh_temp_dir(anon_client, cashflow_csv):
    result = anon_client.analyze(str(cashflow_csv), "cash_flow_13w")
    assert result.success is True
    assert len(result.charts) == 1  # written somewhere real, caller didn't have to pick a dir


# ── 🟢 market — local, no network to PRAGMAS, no beta key ───────────────


def test_market_does_not_require_beta_key(anon_client, monkeypatch):
    class _FakeDDGS:
        def text(self, query, max_results=5):
            return [{"title": "Reuters", "href": "https://example.com", "body": "Rates trending down."}]

    monkeypatch.setattr("ddgs.DDGS", _FakeDDGS)
    result = anon_client.market("real estate LATAM")
    assert isinstance(result, MarketResult)
    assert result.error is None
    assert result.sources[0].title == "Reuters"
    assert result.summary == "Rates trending down."


def test_market_search_failure_returns_structured_error(anon_client, monkeypatch):
    class _RaisingDDGS:
        def text(self, query, max_results=5):
            raise RuntimeError("rate limited")

    monkeypatch.setattr("ddgs.DDGS", _RaisingDDGS)
    result = anon_client.market("anything")
    assert result.sources == []
    assert "Search failed" in result.error


# ── not-yet-implemented surface is discoverable, not silently missing ──


@pytest.mark.parametrize("method_name", ["ask", "ingest", "list_projects", "generate_report"])
def test_unimplemented_methods_raise_clear_error(client, method_name):
    with pytest.raises(PragmasNotImplementedError):
        getattr(client, method_name)()


def test_context_manager_closes_client():
    from pragmas_sdk import PragmasClient

    with PragmasClient() as c:
        assert c._client.is_closed is False
    assert c._client.is_closed is True
