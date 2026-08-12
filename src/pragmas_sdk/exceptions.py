"""Exceptions raised by the PRAGMAS SDK.

Every error the API can plausibly return gets its own type so callers can
`except PragmasAuthError` instead of string-matching messages.
"""
from __future__ import annotations


class PragmasError(Exception):
    """Base class for every error this SDK raises."""


class PragmasAPIError(PragmasError):
    """The API responded with an error status code.

    Attributes:
        status_code: HTTP status code returned by the API.
        detail: The error detail/message the API sent, if any.
    """

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"PRAGMAS API error {status_code}: {detail}".strip())


class PragmasAuthError(PragmasAPIError):
    """Raised on 401/403 — missing, invalid, or expired beta key."""


class PragmasNotFoundError(PragmasAPIError):
    """Raised on 404 — project, template, or resource doesn't exist."""


class PragmasRateLimitError(PragmasAPIError):
    """Raised on 429 — caller is hitting the shared beta rate limit."""


class PragmasConnectionError(PragmasError):
    """Raised when the API can't be reached at all (network/DNS/timeout)."""


class PragmasNotImplementedError(PragmasError):
    """Raised for SDK methods that target a planned-but-not-yet-live endpoint.

    See CONTRACT.md — this is deliberate: the SDK's public surface documents
    where the product is going without pretending an endpoint works today.
    """
