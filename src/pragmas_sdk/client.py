"""Synchronous client for the PRAGMAS API.

See CONTRACT.md for exactly which endpoints are live in production today
versus planned — the docstring on each method repeats that status so it's
visible from `help(client.analyze)` too, not just in the repo.
"""
from __future__ import annotations

import httpx

from pragmas_sdk.exceptions import (
    PragmasAPIError,
    PragmasAuthError,
    PragmasConnectionError,
    PragmasNotFoundError,
    PragmasNotImplementedError,
    PragmasRateLimitError,
)
from pragmas_sdk.models import AnalysisResult, BetaKey, MarketResult, WaitlistResult

DEFAULT_BASE_URL = "https://api.pragmas.io"


class PragmasClient:
    """Client for the PRAGMAS API.

    Args:
        base_url: API root. Defaults to production; point at
            `http://127.0.0.1:8765` for local backend development.
        beta_key: Bearer token from `request_beta_key()`. Optional — only
            required for endpoints that touch a specific account/project
            (`analyze`). Not required for `join_waitlist` or `market`.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        beta_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.beta_key = beta_key
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def __enter__(self) -> "PragmasClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _auth_headers(self) -> dict[str, str]:
        if not self.beta_key:
            raise PragmasAuthError(401, "No beta key set — call request_beta_key() or pass beta_key= to PragmasClient()")
        return {"Authorization": f"Bearer {self.beta_key}"}

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise PragmasConnectionError(f"Timed out calling {path}") from exc
        except httpx.ConnectError as exc:
            raise PragmasConnectionError(
                f"Could not reach {self.base_url}{path} — is the API up? ({exc})"
            ) from exc

        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = resp.text[:300]
            if resp.status_code in (401, 403):
                raise PragmasAuthError(resp.status_code, detail)
            if resp.status_code == 404:
                raise PragmasNotFoundError(resp.status_code, detail)
            if resp.status_code == 429:
                raise PragmasRateLimitError(resp.status_code, detail)
            raise PragmasAPIError(resp.status_code, detail)
        return resp

    # ── 🟢 live today ──────────────────────────────────────────────

    def join_waitlist(self, email: str) -> WaitlistResult:
        """Join the PRAGMAS waitlist. Live in production — no auth needed.

        See CONTRACT.md: `POST /waitlist`.
        """
        resp = self._request("POST", "/waitlist", json={"email": email})
        return WaitlistResult.model_validate(resp.json())

    # ── 🟡 planned, targets the documented-but-not-yet-shipped contract ──

    def request_beta_key(self, email: str) -> BetaKey:
        """Request a free beta key for CLI/SDK access.

        Planned endpoint — see CONTRACT.md `POST /auth/beta-key`. Will raise
        `PragmasConnectionError`/`PragmasNotFoundError` against today's
        production backend until that endpoint ships (GTM plan Phase 0).
        Not gated by a paid plan: no scopes, no billing limits.
        """
        resp = self._request("POST", "/auth/beta-key", json={"email": email})
        key = BetaKey.model_validate(resp.json())
        self.beta_key = key.beta_key
        return key

    def analyze(self, project_id: str, template: str, params: dict | None = None) -> AnalysisResult:
        """Run a deterministic analysis template against a project's data.

        No LLM in the loop — calls `backend/services/analysis_modules/`
        directly once the endpoint ships. Planned — see CONTRACT.md
        `POST /projects/{project_id}/analyze`. Requires a beta key.

        Args:
            project_id: The project to analyze.
            template: One of `ecommerce_unit_economics`, `saas_metrics`,
                `cash_flow_13w`, or `r:seasonality` / `r:outliers` /
                `r:correlations` (the `r:*` templates need R installed on
                the backend host and degrade the same way the backend's own
                test suite already does when it isn't).
            params: Template-specific parameters, forwarded as-is.
        """
        resp = self._request(
            "POST",
            f"/projects/{project_id}/analyze",
            json={"template": template, "params": params or {}},
            headers=self._auth_headers(),
        )
        return AnalysisResult.model_validate(resp.json())

    def market(self, topic: str, max_results: int = 5) -> MarketResult:
        """Search public/macro information on a topic.

        Wraps the agent's real `web_search` tool (DuckDuckGo-backed, no API
        key) — touches no tenant data, so it's the one call in this SDK that
        doesn't need a beta key. Planned — see CONTRACT.md `GET /market`
        (today that path is a hardcoded stub in production).
        """
        resp = self._request("GET", "/market", params={"topic": topic, "max_results": max_results})
        return MarketResult.model_validate(resp.json())

    # ── not in this SDK yet — see CONTRACT.md "Not yet in this SDK" ──

    def ask(self, *args: object, **kwargs: object) -> None:
        """Not implemented yet.

        Scoped to ship after the beta-key flow above is live and the
        agent/RAG path has been verified end-to-end in production. See
        CONTRACT.md.
        """
        raise PragmasNotImplementedError(
            "client.ask() targets the agent/streaming endpoint, which this SDK doesn't "
            "wrap yet — see CONTRACT.md 'Not yet in this SDK'."
        )

    def ingest(self, *args: object, **kwargs: object) -> None:
        """Not implemented yet. See CONTRACT.md 'Not yet in this SDK'."""
        raise PragmasNotImplementedError(
            "client.ingest() isn't wrapped yet — see CONTRACT.md 'Not yet in this SDK'."
        )

    def list_projects(self, *args: object, **kwargs: object) -> None:
        """Not implemented yet. See CONTRACT.md 'Not yet in this SDK'."""
        raise PragmasNotImplementedError(
            "client.list_projects() isn't wrapped yet — see CONTRACT.md 'Not yet in this SDK'."
        )

    def generate_report(self, *args: object, **kwargs: object) -> None:
        """Not implemented yet. See CONTRACT.md 'Not yet in this SDK'."""
        raise PragmasNotImplementedError(
            "client.generate_report() isn't wrapped yet — see CONTRACT.md 'Not yet in this SDK'."
        )
