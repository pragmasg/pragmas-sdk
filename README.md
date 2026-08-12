# pragmas-sdk

Official Python client for the [PRAGMAS](https://pragmas.io) API — an
operational intelligence platform: financial/ops analysis templates, public
market search, and (soon) a conversational agent grounded in your own
documents.

This client is MIT-licensed and open source on purpose: the backend it talks
to isn't. See [CONTRACT.md](./CONTRACT.md) for exactly which endpoints are
live in production today versus planned — this SDK is honest about the
difference rather than pretending everything already works.

## Install

```bash
pip install pragmas-sdk
```

(Not published to PyPI yet — this is pre-release. For now, install from a
local checkout: `pip install -e .`)

## Quickstart

```python
from pragmas_sdk import PragmasClient

client = PragmasClient()

# 🟢 live today, no auth needed
client.join_waitlist("you@example.com")

# 🟡 planned — see CONTRACT.md. Get a free beta key (no plan, no billing).
key = client.request_beta_key("you@example.com")

# 🟡 planned — deterministic, no LLM in the loop
result = client.analyze("your-project-id", "cash_flow_13w")
print(result.results)

# 🟡 planned — no auth required, touches no tenant data
market = client.market("interest rates real estate LATAM")
print(market.summary)
```

## Status

This is a **beta feedback tool**, not a monetized product surface — see the
PRAGMAS GTM plan. The goal right now is technical feedback on the shape of
these commands, not conversion. Expect the contract to change; expect some
methods (`ask`, `ingest`, `list_projects`, `generate_report`) to raise
`PragmasNotImplementedError` until their endpoints ship.

Feedback: open an issue on this repo.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests mock the HTTP layer with `respx` — no live backend required to run them.

## License

MIT — see [LICENSE](./LICENSE).
