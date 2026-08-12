"""Response models. Mirrors the shapes documented in CONTRACT.md exactly —
if the backend contract changes, update both together.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WaitlistResult(BaseModel):
    ok: bool
    message: str


class BetaKey(BaseModel):
    beta_key: str
    email: str
    created_at: str


class AnalysisResult(BaseModel):
    success: bool
    module: str
    results: dict[str, Any] = {}
    charts: list[str] = []
    error: str | None = None


class MarketSource(BaseModel):
    title: str
    url: str
    snippet: str = ""


class MarketResult(BaseModel):
    topic: str
    summary: str
    sources: list[MarketSource] = []
    generated_at: str | None = None
