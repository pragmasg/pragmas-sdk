# API contract

Most of this SDK doesn't talk to a backend at all — `analyze()` and `market()`
run entirely on your machine (see below). The two methods that do
(`join_waitlist`, `request_beta_key`) hit the PRAGMAS backend (`noname` repo,
private), and this document is the source of truth for their exact shape and
— critically — **which of them exist in production today versus which are
planned**. Keep this in sync with the backend as each endpoint actually ships;
don't let the SDK claim more than the backend can deliver.

Status legend: 🟢 live/works today · 🟡 planned, not yet implemented backend-side.

## 🟢 `analyze()` and `market()` — local, no backend contract at all

These don't call any PRAGMAS server, so there's no endpoint to document here —
that's the point. `analyze()` runs `pragmas_sdk.analysis` (vendored from the
backend's `services/analysis_modules/`, kept in sync by hand) directly on your
machine: deterministic pandas/R financial math, no proprietary model behind
it, so routing it through a server would only add latency, a network
dependency, and cost for no benefit. `market()` calls DuckDuckGo directly (no
API key) from wherever the code runs — same reasoning, plus it never touches
tenant data, so there was never a reason to put a PRAGMAS server in the
middle.

Practical effect: neither needs a beta key, and both work with the backend
completely down (a real backend endpoint for `analyze`-equivalent
functionality may still exist someday for the *web app*, whose browser users
can't run local Python — but that's a separate, later decision, unrelated to
this SDK).

Dependencies this pulls in that a pure network-only client wouldn't need:
`pandas`, `matplotlib` (both required), `ddgs` (required), and
`Rscript` installed *locally* for the `r:*` templates only (optional —
everything else works without it, and `r:*` degrades to a clear error if it's
missing, same as the old server-side version used to).

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

## Not yet in this SDK

`projects`, `documents`/ingest, `agent`/`ask` (streaming), `reports` all have
real backend endpoints already (see `backend/routers/`), but wrapping them is
scoped to a later pass once the beta-key auth flow above is live and the
agent/RAG path has been verified end-to-end in production (it hasn't, as of
this writing — Railway has been down). Wrapping them before that would ship
client methods nobody can actually use yet.

## History

`analyze()`/`market()` were originally designed as planned backend endpoints
(`POST /projects/{id}/analyze`, `GET /market`) — see git history if you want
that version. Moved to local execution instead once it became clear a public,
zero-auth `/market` and a per-call-billed `/analyze` were real cost/abuse
surface for no actual benefit (neither needs a server to do its job).
