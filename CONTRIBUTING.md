# Contributing to pragmas-sdk

Thanks for considering it. This doc exists so you know what to touch, what
not to touch, and what to expect before you spend time on a PR.

## Where this fits

`pragmas-sdk` is the open-source client for the local, deterministic parts
of [PRAGMAS](https://pragmas.io): analysis templates and public-research
search. It does not include the hosted AI agent, document ingestion, or
report generation — those aren't part of this repo, and PRs that try to
reverse-engineer or reimplement them here are out of scope.

`CONTRACT.md` documents which methods are implemented here versus planned —
check it before assuming a method exists.
[`pragmas-cli`](https://github.com/pragmasg/pragmas-cli) is a separate repo
built on top of this SDK; if what you want to add is a terminal command or
UX improvement rather than a Python capability, it belongs there instead.

## Scope right now

The SDK's local capabilities (analysis templates, `market()`) are open for
contribution — see the table below. Connectors and other new extension
points aren't formalized yet: we're waiting for a few real proposals before
designing an interface, rather than building a contract against nobody's
actual use case and having to redo it later. See
[Proposing a connector / new extension point](#proposing-a-connector--a-new-extension-point-not-yet-formalized)
below for what to do if you want one anyway.

One thing worth knowing: `pragmas_sdk/analysis/` is currently a
**hand-vendored copy**, kept in sync by a maintainer rather than shared via
import — see the module docstring in `pragmas_sdk/analysis/__init__.py` and
`CONTRACT.md`'s "History" section. Changes you make here land in the SDK/CLI
for everyone using them right away.

## What you can contribute today

| Area | Status | Notes |
|---|---|---|
| New analysis template (Python) | 🟢 open | See below |
| New analysis template (R) | 🟢 open, but fixed-whitelist only | See below — no arbitrary R execution, ever |
| Bug fixes in existing templates / `client.py` / `models.py` | 🟢 open | |
| Docs (README, CONTRACT.md, docstrings) | 🟢 open | Keep the 🟢/🟡/⚪ status legend honest — don't upgrade a status without checking the backend actually supports it |
| New connector, exporter, or other new extension point | 🟡 open an issue first | Interface isn't formalized yet — see below |
| Anything touching `ask`/`ingest`/`list_projects`/`generate_report` | ⚪ not yet | Not implemented in this SDK — out of scope for now |

### Adding an analysis template (Python)

Follow the existing modules (`saas_metrics.py`, `cash_flow_13w.py`,
`ecommerce_unit_economics.py`) as the pattern:

1. New file under `src/pragmas_sdk/analysis/`, using `pragmas_sdk.analysis.base`
   helpers (`load_csv` for validated input, `save_chart` for matplotlib
   figures, `package_result` for the standard output shape).
2. Signature: `run_<name>(input_csv, params: dict, output_dir) -> dict`,
   returning `{"success", "module", "results", "charts", "error"}` —
   `package_result` builds this for you.
3. **Never raise on bad input or bad params** — catch it and return
   `error=...` instead (see `AnalysisInputError` usage in existing modules).
   Callers (the CLI, other integrations) rely on `result.success`/`.error`,
   not exceptions, for anything data-related.
4. Register it in `MODULES` in `src/pragmas_sdk/analysis/__init__.py`.
5. Add tests in `tests/` — real pandas/matplotlib runs, no mocking (that's
   the existing convention; these are deterministic, so there's no reason to
   fake them).
6. Add it to the template table in `README.md`.

### Adding an analysis template (R)

Same shape, extra constraint: **only fixed, whitelisted templates ever run —
never arbitrary R code**, by design (see the module docstring in
`r_runner.py`). To add one:

1. New `.R` file under `src/pragmas_sdk/analysis/r_templates/`, following
   `seasonality.R`/`outliers.R`/`correlations.R` as the pattern (reads
   `input.csv` + `params.json` from the working directory, writes
   `results.json` and `chart_*.png`/`chart_*.pdf`).
2. Add an entry to the `R_TEMPLATES` dict in `r_runner.py` — this dict *is*
   the whitelist; nothing outside it can run.
3. Tests should cover the error/whitelist paths without requiring R
   installed (existing convention — see `tests/`); a real `Rscript` run only
   executes if R happens to be installed on the machine running the suite.

A PR that tries to let a template execute arbitrary/user-supplied R (or
shell) instead of a fixed template file will be rejected regardless of how
useful the feature sounds — that's a deliberate security boundary, not an
oversight.

### Proposing a connector / a new extension point (not yet formalized)

The README documents a connector roadmap (Salesforce, GA4, Shopify,
WordPress) — none of it is built, and there is **no `Connector` interface
yet**. Rather than have you write a full implementation against an interface
we might redesign, [open an issue](https://github.com/pragmasg/pragmas-sdk/issues)
first describing:

- What data source you want to connect.
- What you'd want `client.analyze_<x>(...)` (or similar) to actually return.
- Whether it needs auth (OAuth, API key) and what that flow would look like.

We're intentionally waiting to see a few real proposals before designing the
interface — a contract designed against nobody's actual use case tends to be
wrong in a way that's expensive to fix later. If you want to prototype
anyway, keep it in your own fork/branch until there's alignment on shape;
we're unlikely to merge a first connector implementation as-is.

The same applies to any other new SDK-level extension point (exporters,
alternative output formats, etc.) that doesn't already have a documented
pattern in this repo.

## What not to contribute here

- Anything that would require reimplementing the hosted AI agent (retrieval,
  orchestration, prompts, document ingestion) — that's not part of this repo
  and out of scope for a PR here.
- API keys, tokens, or credentials of any kind, in code, tests, or examples.
- Changes to `CONTRACT.md` that mark something 🟢 without it actually being
  verified live — the whole point of that file is that its status legend is
  trustworthy.

## Development setup

```bash
git clone https://github.com/pragmasg/pragmas-sdk.git
cd pragmas-sdk
pip install -e ".[dev]"
pytest
```

Requires Python 3.9+. `analyze()`'s Python templates run for real in tests
(pandas/matplotlib, no mocking — they're deterministic, so there's nothing
to gain from faking them). The R-backed templates' sandboxing/whitelist/error
paths are tested without R installed; a real `Rscript` run only happens if R
is present on your machine. `join_waitlist`/`request_beta_key` tests mock the
HTTP layer with [`respx`](https://lundberg.github.io/respx/) — no live
backend required for any of this.

## Opening a PR

1. For anything beyond a small fix, open an issue first — saves you from
   building something that's out of scope for this repo (see above).
2. Branch off `master`, keep the PR focused on one thing.
3. Make sure `pytest` passes locally.
4. If you touched `README.md`'s status table or `CONTRACT.md`, make sure the
   status you claimed is actually accurate — a maintainer will check this
   against the live backend before merging.
5. Describe what you tested and how, especially for anything without a
   backend to verify against.

There's no CLA — contributions are accepted under this repo's MIT license
(see [LICENSE](./LICENSE)), same as the rest of the code.

## Reporting bugs / requesting features

[Open an issue](https://github.com/pragmasg/pragmas-sdk/issues) — that's also
where connector/template requests and general feedback go, same tracker
`pragmas feedback` in the CLI points to.

## Code of conduct

Be respectful, assume good faith, keep discussion about the code and the
product. Anything else gets moderated on a normal-sense basis — there's no
separate formal policy document for this repo yet.
