"""Client for the PRAGMAS SDK.

`analyze()` and `market()` run entirely on your machine — no network call to
any PRAGMAS server, no account, no beta key. `join_waitlist()` and
`request_beta_key()` are the only two methods that talk to the real backend
(see CONTRACT.md for their exact status). See the package docstring in
`pragmas_sdk.analysis` for why `analyze()` is local by design, not just for
now: it's deterministic financial math with no proprietary model behind it,
so there's no reason to route it through a server at all — doing so would
only add latency, a network dependency, and cost for something that runs
just as well, more privately, on your own machine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import httpx

from pragmas_sdk.analysis import run_module
from pragmas_sdk.exceptions import (
    PragmasAPIError,
    PragmasAuthError,
    PragmasConnectionError,
    PragmasNotFoundError,
    PragmasNotImplementedError,
    PragmasRateLimitError,
)
from pragmas_sdk.models import AnalysisResult, BetaKey, MarketResult, MarketSource, WaitlistResult

DEFAULT_BASE_URL = "https://api.pragmas.io"


class PragmasClient:
    """Client for the PRAGMAS API and its local analysis templates.

    Args:
        base_url: API root, only used by `join_waitlist`/`request_beta_key`.
            Defaults to production; point at `http://127.0.0.1:8765` for
            local backend development.
        beta_key: Bearer token from `request_beta_key()`. Not required for
            anything in this SDK today — kept for the future `ask`/`ingest`/
            `generate_report` methods, which will need it once they ship.
        timeout: Request timeout in seconds, for the two network methods.
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

    # ── 🟢 live today, over the network ───────────────────────────

    def join_waitlist(self, email: str) -> WaitlistResult:
        """Join the PRAGMAS waitlist. Live in production — no auth needed.

        See CONTRACT.md: `POST /waitlist`.
        """
        resp = self._request("POST", "/waitlist", json={"email": email})
        return WaitlistResult.model_validate(resp.json())

    def request_beta_key(self, email: str) -> BetaKey:
        """Request a free beta key for the future `ask`/`ingest`/`generate_report`.

        Planned endpoint — see CONTRACT.md `POST /auth/beta-key`. Not needed
        for `analyze()` or `market()`, which run locally. Not gated by a
        paid plan: no scopes, no billing limits.
        """
        resp = self._request("POST", "/auth/beta-key", json={"email": email})
        key = BetaKey.model_validate(resp.json())
        self.beta_key = key.beta_key
        return key

    # ── 🟢 local — no network, no account ─────────────────────────

    def analyze(
        self,
        input_csv: str,
        template: str,
        params: dict[str, Any] | None = None,
        output_dir: str | None = None,
    ) -> AnalysisResult:
        """Run a deterministic analysis template against a local CSV.

        Runs entirely on your machine via `pragmas_sdk.analysis` — no
        network call, no account. Never raises for bad input or an unknown
        template; check `result.success`/`result.error` instead, same as
        every function in `pragmas_sdk.analysis` already does.

        Args:
            input_csv: Path to a local CSV file.
            template: One of `ecommerce_unit_economics`, `saas_metrics`,
                `cash_flow_13w`, or `r:seasonality` / `r:outliers` /
                `r:correlations` (the `r:*` templates need `Rscript`
                installed locally; everything else doesn't).
            params: Template-specific parameters.
            output_dir: Where to write `results.json` and any charts.
                Defaults to a fresh temp directory (the path is on
                `result.charts` either way).
        """
        out_dir = Path(output_dir) if output_dir else Path(mkdtemp(prefix="pragmas_analysis_"))
        result = run_module(template, input_csv, params or {}, out_dir)
        return AnalysisResult.model_validate(result)

    def market(self, topic: str, max_results: int = 5) -> MarketResult:
        """Search public information on a topic.

        Runs locally via DuckDuckGo (no API key) — no network call to any
        PRAGMAS server, no account, touches no tenant data. Never raises on
        a failed search; check `result.error` instead.
        """
        generated_at = datetime.now(timezone.utc).isoformat()
        try:
            from ddgs import DDGS

            raw = list(DDGS().text(topic, max_results=max_results))
        except Exception as exc:  # noqa: BLE001 — never crash the caller
            return MarketResult(
                topic=topic, summary="", sources=[], generated_at=generated_at,
                error=f"Search failed: {exc}",
            )

        sources = [
            MarketSource(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=(r.get("body") or "")[:500],
            )
            for r in raw
        ]
        summary = sources[0].snippet if sources else ""
        return MarketResult(topic=topic, summary=summary, sources=sources, generated_at=generated_at)

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
