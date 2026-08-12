# pragmas-sdk

**The Python client for [PRAGMAS](https://pragmas.io)** — an operational
intelligence platform that turns business documents (PDF, Excel, Word, PPTX,
CSV) into a RAG-grounded agent you can ask questions, deterministic financial
analysis (SaaS metrics, e-commerce unit economics, 13-week cash flow,
R-backed seasonality/outlier/correlation analysis), and PDF/PPTX reports.

[![PyPI version](https://img.shields.io/pypi/v/pragmas-sdk.svg)](https://pypi.org/project/pragmas-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/pragmas-sdk.svg)](https://pypi.org/project/pragmas-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The PRAGMAS backend is closed source. This client is MIT and open on
purpose: we want real feedback on the API's shape from early technical
adopters before the platform goes GA, not to monetize the client itself.
See [`pragmas-cli`](https://github.com/pragmasg/pragmas-cli) for the terminal
counterpart built directly on top of this SDK.

## Install

```bash
pip install pragmas-sdk
```

Requires Python 3.9+.

## Quickstart

The waitlist is the one endpoint that's actually live in production today —
zero auth, zero setup:

```python
from pragmas_sdk import PragmasClient

client = PragmasClient()
result = client.join_waitlist("you@example.com")
print(result)
# WaitlistResult(ok=True, message='...')
```

Everything else below targets the contract the backend is shipping next —
call it today and you'll get a clear `PragmasConnectionError` or
`PragmasNotFoundError` instead of a silent failure:

```python
# 🟡 planned — free beta key, no plan or billing gate
key = client.request_beta_key("you@example.com")

# 🟡 planned — deterministic template, no LLM in the loop
result = client.analyze("your-project-id", "cash_flow_13w")
print(result.results)

# 🟡 planned — no auth required, touches no tenant data
market = client.market("interest rates real estate LATAM")
print(market.summary)
```

## Status

`PragmasClient` is honest about what it can actually do against production
right now. This table is kept in sync with [`CONTRACT.md`](./CONTRACT.md),
the source of truth.

| Method | Backend endpoint | Status |
|---|---|---|
| `join_waitlist(email)` | `POST /waitlist` | 🟢 live |
| `request_beta_key(email)` | `POST /auth/beta-key` | 🟡 planned |
| `analyze(project_id, template, params=None)` | `POST /projects/{id}/analyze` | 🟡 planned |
| `market(topic, max_results=5)` | `GET /market` | 🟡 planned (today it's a hardcoded stub) |
| `ask()`, `ingest()`, `list_projects()`, `generate_report()` | — | ⚪ not wrapped yet — raise `PragmasNotImplementedError` |

🟢 live · 🟡 endpoint planned, calling it against production today raises
a connection/API error · ⚪ no backend contract targeted yet in this SDK.

## `analyze()` templates

`template` is one of:

- `saas_metrics`
- `ecommerce_unit_economics`
- `cash_flow_13w`
- `r:seasonality`, `r:outliers`, `r:correlations` — R-backed, require
  `Rscript` on the backend host

## Response shapes

Pydantic models, so you get autocomplete and validation for free.
`AnalysisResult`, from `client.analyze("acme", "cash_flow_13w")`:

```json
{
  "success": true,
  "module": "cash_flow_13w",
  "results": { "weeks": 13 },
  "charts": ["chart1.png"],
  "error": null
}
```

`MarketResult`, from `client.market("real estate LATAM")`:

```json
{
  "topic": "real estate LATAM",
  "summary": "Rates trending down.",
  "sources": [
    { "title": "Reuters", "url": "https://example.com", "snippet": "..." }
  ],
  "generated_at": "2026-08-01T00:00:00Z"
}
```

## Error handling

Every failure mode gets its own exception type, all subclasses of
`PragmasError`, so you can catch precisely instead of string-matching:

```python
from pragmas_sdk import PragmasAuthError, PragmasConnectionError, PragmasNotFoundError

try:
    client.analyze("acme", "cash_flow_13w")
except PragmasAuthError:
    ...  # 401/403 — missing or expired beta key
except PragmasNotFoundError:
    ...  # 404 — project or template doesn't exist
except PragmasConnectionError:
    ...  # network/DNS/timeout — API unreachable
```

`PragmasRateLimitError` (429) and `PragmasAPIError` (any other 4xx/5xx) round
out the set. `PragmasNotImplementedError` is raised client-side, before any
request goes out, for methods that don't target a shipped endpoint yet.

## What's next

Once the beta-key flow and the deterministic-analysis endpoint above are
live and the agent/RAG path has been verified end-to-end in production,
this SDK grows real methods for:

- `ask` — the conversational agent, streaming
- `ingest` — document upload (PDF/Excel/Word/PPTX/CSV)
- `list_projects`
- `generate_report` — PDF/PPTX report generation

Wrapping those before the backend can serve them would ship client methods
nobody could actually use — so they raise `PragmasNotImplementedError` for
now, on purpose, rather than being silently missing.

## Give feedback

This SDK exists to get its design right before the platform goes GA — the
fastest way to influence it is to tell us what's awkward, missing, or
surprising. [Open an issue](https://github.com/pragmasg/pragmas-sdk/issues).

## Development

```bash
git clone https://github.com/pragmasg/pragmas-sdk.git
cd pragmas-sdk
pip install -e ".[dev]"
pytest
```

Tests mock the HTTP layer with [`respx`](https://lundberg.github.io/respx/)
— no live backend required to run them.

## License

MIT — see [LICENSE](./LICENSE).
