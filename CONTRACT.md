# API contract

This SDK talks to the PRAGMAS backend (`noname` repo, private). This document is
the single source of truth for which endpoints it calls, their shape, and —
critically — **which of them exist in production today versus which are planned**.
Keep this in sync with the backend as each endpoint actually ships; don't let the
SDK claim more than the backend can deliver.

Status legend: 🟢 live today · 🟡 planned, not yet implemented backend-side.

## 🟢 `POST /waitlist` — live today

```
POST /waitlist
{ "email": "user@example.com" }

201 { "ok": true, "message": "..." }
422 { "detail": "Invalid email" }
```

Source: `backend/routers/waitlist.py`. No auth required.

> **Note:** this endpoint's responses used to be hardcoded Spanish (`"Email no
> válido"`, `"Te avisaremos..."`) even though this SDK/CLI pair is English-only.
> Fixed backend-side on branch `fix/backend-english-responses`, not yet merged to
> `fase-a-fixes`/deployed — the shape above is the corrected one this SDK targets.

## 🟡 `POST /auth/beta-key` — planned (GTM plan Phase 0)

Free, unauthenticated-except-for-email issuance of a bearer token for CLI/SDK
use during the technical-feedback beta. **Not gated by a paid plan** — see the
GTM plan's "beta key" decision. Modeled after the existing `TokenResponse`
shape in `backend/routers/auth.py` for consistency.

```
POST /auth/beta-key
{ "email": "user@example.com" }

201 { "beta_key": "pk_beta_...", "email": "user@example.com", "created_at": "2026-08-01T00:00:00Z" }
```

Subsequent authenticated calls send `Authorization: Bearer <beta_key>`.

## 🟡 `POST /projects/{project_id}/analyze` — planned (GTM plan Phase 1)

Invokes `backend/services/analysis_modules/` directly — deterministic, no LLM
in the loop. The module contract already exists and is tested
(`backend/tests/analysis/test_analysis_modules.py`); this endpoint is the first
thing that calls it over HTTP.

```
POST /projects/{project_id}/analyze
Authorization: Bearer <beta_key>
{ "template": "cashflow-13w", "params": {} }

200 {
  "success": true,
  "module": "cash_flow_13w",
  "results": { ... },
  "charts": ["..."],
  "error": null
}
```

`template` is one of `list_modules()` from `analysis_modules/__init__.py`:
`ecommerce_unit_economics`, `saas_metrics`, `cash_flow_13w`, or `r:<name>` for
the R-backed templates (`r:seasonality`, `r:outliers`, `r:correlations` —
these require `Rscript` on the backend host and degrade the same way the
existing test suite already does when R isn't installed).

## 🟡 `GET /market` — planned (GTM plan Phase 1, replaces the existing stub)

`GET /market` already exists in `backend/routers/analytics.py` but is a
hardcoded stub (`{"trends": [], "insights": [], "last_updated": None}`). This
contract is what it should become: a thin wrapper over the `web_search` agent
tool (DuckDuckGo-backed, no API key), safe to expose publicly since it touches
no tenant data.

```
GET /market?topic=...&max_results=5

200 {
  "topic": "...",
  "summary": "...",
  "sources": [{ "title": "...", "url": "...", "snippet": "..." }],
  "generated_at": "2026-08-01T00:00:00Z"
}
```

No auth required (candidate for the CLI's zero-friction command — see GTM plan).

## Not yet in this SDK

`projects`, `documents`/ingest, `agent`/`ask` (streaming), `reports` all have
real backend endpoints already (see `backend/routers/`), but wrapping them is
scoped to a later pass once the beta-key auth flow above is live and the
agent/RAG path has been verified end-to-end in production (it hasn't, as of
this writing — Railway has been down). Wrapping them before that would ship
client methods nobody can actually use yet.
