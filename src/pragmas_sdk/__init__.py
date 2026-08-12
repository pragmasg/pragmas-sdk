"""Official Python client for the PRAGMAS API.

    from pragmas_sdk import PragmasClient

    client = PragmasClient()
    client.join_waitlist("you@example.com")

See CONTRACT.md in the repo root for which endpoints are live today versus
planned.
"""
from pragmas_sdk.client import PragmasClient
from pragmas_sdk.exceptions import (
    PragmasAPIError,
    PragmasAuthError,
    PragmasConnectionError,
    PragmasError,
    PragmasNotFoundError,
    PragmasNotImplementedError,
    PragmasRateLimitError,
)
from pragmas_sdk.models import AnalysisResult, BetaKey, MarketResult, MarketSource, WaitlistResult

__version__ = "0.1.0"

__all__ = [
    "PragmasClient",
    "PragmasError",
    "PragmasAPIError",
    "PragmasAuthError",
    "PragmasConnectionError",
    "PragmasNotFoundError",
    "PragmasNotImplementedError",
    "PragmasRateLimitError",
    "AnalysisResult",
    "BetaKey",
    "MarketResult",
    "MarketSource",
    "WaitlistResult",
    "__version__",
]
