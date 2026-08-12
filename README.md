# pragmas-sdk

**The Python client for [PRAGMAS](https://pragmas.io)** — an operational
intelligence platform. This package runs deterministic financial analysis
(SaaS metrics, e-commerce unit economics, 13-week cash flow, R-backed
seasonality/outlier/correlation analysis) and public market search **entirely
on your machine** — no account, no network call to any PRAGMAS server, your
data never leaves your computer. The RAG-grounded agent and document ingestion
are a thin client around the (closed-source, hosted) backend instead, coming
once that path is live.

[![PyPI version](https://img.shields.io/pypi/v/pragmas-sdk.svg)](https://pypi.org/project/pragmas-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/pragmas-sdk.svg)](https://pypi.org/project/pragmas-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The PRAGMAS backend is closed source. This client is MIT and open on
purpose: we want real feedback on its shape from early technical adopters
before the platform goes GA, not to monetize the client itself. See
[`pragmas-cli`](https://github.com/pragmasg/pragmas-cli) for the terminal
counterpart built directly on top of this SDK.

## Install

```bash
pip install pragmas-sdk
```

Requires Python 3.9+.

## Quickstart

`analyze()` and `market()` need nothing — no account, no API key, no internet
access to any PRAGMAS server:

```python
from pragmas_sdk import PragmasClient

client = PragmasClient()

result = client.analyze("cashflow.csv", "cash_flow_13w")
print(result.results["min_balance"], result.charts)

market = client.market("interest rates real estate LATAM")
print(market.summary)
```

`join_waitlist()` is the one call that's actually live against the real
backend today — still zero setup:

```python
client.join_waitlist("you@example.com")
```

## Status

`PragmasClient` is honest about what it can actually do right now. This table
is kept in sync with [`CONTRACT.md`](./CONTRACT.md), the source of truth.

| Method | Runs | Status |
|---|---|---|
| `analyze(input_csv, template, params=None, output_dir=None)` | locally | 🟢 works today, no network |
| `market(topic, max_results=5)` | locally | 🟢 works today, no network |
| `join_waitlist(email)` | `POST /waitlist` | 🟢 live in production |
| `request_beta_key(email)` | `POST /auth/beta-key` | 🟡 planned |
| `ask()`, `ingest()`, `list_projects()`, `generate_report()` | — | ⚪ not wrapped yet — raise `PragmasNotImplementedError` |

🟢 works today · 🟡 targets a documented but not-yet-shipped backend endpoint
· ⚪ no backend contract targeted yet in this SDK.

## `analyze()` templates

`template` is one of:

- `saas_metrics`
- `ecommerce_unit_economics`
- `cash_flow_13w`
- `r:seasonality`, `r:outliers`, `r:correlations` — R-backed, require
  `Rscript` **installed on your own machine** (everything else needs nothing
  beyond `pip install`)

Never raises on bad input, an unknown template, or missing `Rscript` — check
`result.success`/`result.error` instead:

```python
result = client.analyze("orders.csv", "ecommerce_unit_economics")
if not result.success:
    print("failed:", result.error)
```

## Response shapes

Pydantic models, so you get autocomplete and validation for free.
`AnalysisResult`, from `client.analyze("cashflow.csv", "cash_flow_13w")`:

```json
{
  "success": true,
  "module": "cash_flow_13w",
  "results": { "weeks": 13, "min_balance": -1000.0 },
  "charts": ["/tmp/pragmas_analysis_xyz/cash_flow_13w.png"],
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
  "generated_at": "2026-08-12T00:00:00+00:00",
  "error": null
}
```

## Error handling

`analyze()` and `market()` never raise for a bad result — they run locally
and always return a model, so check `.error`/`.success` (shown above). The
two methods that go over the network (`join_waitlist`, `request_beta_key`)
raise real exceptions instead, each a subclass of `PragmasError` so you can
catch precisely:

```python
from pragmas_sdk import PragmasConnectionError, PragmasAPIError

try:
    client.request_beta_key("you@example.com")
except PragmasConnectionError:
    ...  # network/DNS/timeout — API unreachable
except PragmasAPIError:
    ...  # any other 4xx/5xx from the backend
```

`PragmasAuthError` (401/403) and `PragmasRateLimitError` (429) round out the
set. `PragmasNotImplementedError` is raised client-side, before any request
goes out, for methods that don't target a shipped endpoint yet.

## What's next

Once the beta-key flow above is live and the agent/RAG path has been
verified end-to-end in production, this SDK grows real methods for:

- `ask` — the conversational agent, streaming
- `ingest` — document upload (PDF/Excel/Word/PPTX/CSV)
- `list_projects`
- `generate_report` — PDF/PPTX report generation

Wrapping those before the backend can serve them would ship client methods
nobody could actually use — so they raise `PragmasNotImplementedError` for
now, on purpose, rather than being silently missing. `analyze()`/`market()`
are staying local for good, not moving to the network later — see
[CONTRACT.md](./CONTRACT.md) for why.

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

`analyze()` tests run for real (pandas/matplotlib, no mocking); the R-backed
templates' sandboxing/whitelist/error paths are tested without R, and a real
`Rscript` run only executes if R is installed on your machine. `join_waitlist`/
`request_beta_key` tests mock the HTTP layer with
[`respx`](https://lundberg.github.io/respx/) — no live backend required.

## License

MIT — see [LICENSE](./LICENSE).
