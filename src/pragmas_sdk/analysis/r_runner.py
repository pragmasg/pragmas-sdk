"""
Runs statistical analyses in R via Rscript.

SAME sandbox philosophy as the rest of this package: ONLY fixed, whitelisted
templates — never arbitrary R code. Each template:
    input:  input.csv (copied to an isolated temp directory) + params
            serialized to params.json
    output: results.json + ggplot2 charts (PNG and PDF) in the tmpdir,
            copied to output_dir

If Rscript isn't installed, returns a structured error (degrades gracefully
instead of crashing). Install R locally to use the R-backed templates:
    - macOS: `brew install r`
    - Debian/Ubuntu: `apt-get install -y r-base r-cran-ggplot2 r-cran-jsonlite`
    - Windows: https://cran.r-project.org/bin/windows/base/
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from pragmas_sdk.analysis.base import package_result

logger = logging.getLogger("pragmas_sdk.analysis.r")

TEMPLATES_DIR = Path(__file__).parent / "r_templates"

# Whitelist: name → .R file. Nothing outside this dict ever runs.
R_TEMPLATES = {
    "seasonality": "seasonality.R",
    "outliers": "outliers.R",
    "correlations": "correlations.R",
}

DEFAULT_TIMEOUT_S = int(os.environ.get("R_ANALYSIS_TIMEOUT", "120"))


def find_rscript() -> Optional[str]:
    return shutil.which(os.environ.get("RSCRIPT_BIN", "Rscript"))


def r_available() -> bool:
    return find_rscript() is not None


def run_r_analysis(
    template: str,
    input_csv,
    params: Dict[str, Any],
    output_dir,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    module = f"r:{template}"
    output_dir = Path(output_dir)

    if template not in R_TEMPLATES:
        return package_result(
            module, output_dir,
            error=f"Unknown R template: {template!r}. "
                  f"Available: {', '.join(sorted(R_TEMPLATES))}",
        )

    rscript = find_rscript()
    if not rscript:
        return package_result(
            module, output_dir,
            error="Rscript is not installed on this machine. "
                  "Install R (r-base + r-cran-ggplot2 + r-cran-jsonlite) to use the "
                  "R-backed templates (r:seasonality, r:outliers, r:correlations) — "
                  "everything else in this SDK works without it.",
        )

    src_csv = Path(input_csv)
    if not src_csv.is_file():
        return package_result(module, output_dir, error=f"Input CSV not found: {src_csv}")

    template_path = TEMPLATES_DIR / R_TEMPLATES[template]
    tmpdir = tempfile.mkdtemp(prefix="pragmas_r_")
    try:
        tmp = Path(tmpdir)
        shutil.copyfile(src_csv, tmp / "input.csv")
        (tmp / "params.json").write_text(
            json.dumps(params or {}, ensure_ascii=False), encoding="utf-8"
        )
        shutil.copyfile(template_path, tmp / "analysis.R")

        proc = subprocess.run(
            [rscript, "--vanilla", "analysis.R"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or proc.stdout or "").splitlines()[-15:])
            return package_result(module, output_dir, error=f"Rscript failed:\n{tail}")

        results_file = tmp / "results.json"
        if not results_file.is_file():
            return package_result(module, output_dir, error="The R template did not produce results.json")
        results = json.loads(results_file.read_text(encoding="utf-8"))

        output_dir.mkdir(parents=True, exist_ok=True)
        charts = []
        for chart in sorted(tmp.glob("chart_*.png")) + sorted(tmp.glob("chart_*.pdf")):
            dest = output_dir / chart.name
            shutil.copyfile(chart, dest)
            charts.append(str(dest))

        return package_result(module, output_dir, results, charts)

    except subprocess.TimeoutExpired:
        return package_result(module, output_dir, error=f"R analysis exceeded the {timeout}s timeout")
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_r_analysis(%s) failed", template)
        return package_result(module, output_dir, error=f"Unexpected error: {exc}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
