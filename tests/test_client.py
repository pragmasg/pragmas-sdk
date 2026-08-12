import httpx
import pytest
import respx

from pragmas_sdk import (
    AnalysisResult,
    BetaKey,
    MarketResult,
    PragmasAuthError,
    PragmasConnectionError,
    PragmasNotFoundError,
    PragmasNotImplementedError,
    PragmasRateLimitError,
    WaitlistResult,
)

BASE = "https://api.pragmas.io"


# ── 🟢 join_waitlist (live endpoint) ──────────────────────────────────


@respx.mock
def test_join_waitlist_success(client):
    respx.post(f"{BASE}/waitlist").mock(
        return_value=httpx.Response(201, json={"ok": True, "message": "Te avisaremos."})
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


# ── 🟡 request_beta_key ────────────────────────────────────────────────


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


# ── 🟡 analyze ──────────────────────────────────────────────────────────


@respx.mock
def test_analyze_success(client):
    respx.post(f"{BASE}/projects/acme/analyze").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "module": "cash_flow_13w",
                "results": {"weeks": 13},
                "charts": ["chart1.png"],
                "error": None,
            },
        )
    )
    result = client.analyze("acme", "cash_flow_13w")
    assert isinstance(result, AnalysisResult)
    assert result.success is True
    assert result.module == "cash_flow_13w"
    assert result.results == {"weeks": 13}


def test_analyze_without_beta_key_raises_before_any_request(anon_client):
    with pytest.raises(PragmasAuthError):
        anon_client.analyze("acme", "cash_flow_13w")


@respx.mock
def test_analyze_unknown_project_raises_not_found(client):
    respx.post(f"{BASE}/projects/ghost/analyze").mock(
        return_value=httpx.Response(404, json={"detail": "Project not found"})
    )
    with pytest.raises(PragmasNotFoundError):
        client.analyze("ghost", "cash_flow_13w")


@respx.mock
def test_analyze_rate_limited(client):
    respx.post(f"{BASE}/projects/acme/analyze").mock(
        return_value=httpx.Response(429, json={"detail": "Too many requests"})
    )
    with pytest.raises(PragmasRateLimitError):
        client.analyze("acme", "cash_flow_13w")


# ── 🟡 market — no auth required ────────────────────────────────────────


@respx.mock
def test_market_does_not_require_beta_key(anon_client):
    respx.get(f"{BASE}/market").mock(
        return_value=httpx.Response(
            200,
            json={
                "topic": "real estate LATAM",
                "summary": "Rates trending down.",
                "sources": [{"title": "Reuters", "url": "https://example.com", "snippet": "..."}],
                "generated_at": "2026-08-01T00:00:00Z",
            },
        )
    )
    result = anon_client.market("real estate LATAM")
    assert isinstance(result, MarketResult)
    assert result.sources[0].title == "Reuters"


# ── connection errors ────────────────────────────────────────────────


@respx.mock
def test_unreachable_backend_raises_connection_error(anon_client):
    respx.get(f"{BASE}/market").mock(side_effect=httpx.ConnectError("nope"))
    with pytest.raises(PragmasConnectionError):
        anon_client.market("anything")


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
