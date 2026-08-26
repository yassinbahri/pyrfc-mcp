"""App-level exception hierarchy for the ADT client, mirroring
rfc_mcp.sap.exceptions' shape (SAPError -> ADTError) so callers can handle
both transports with a consistent pattern without needing to know which
transport a given tool call used.
"""

from __future__ import annotations

import httpx


class ADTError(Exception):
    """Base class for all ADT-related errors raised by this server."""


class ADTNotConfiguredError(ADTError):
    """RFC_MCP_ADT_ENABLED is not true — the ADT client was never built."""


class ADTConnectionError(ADTError):
    """Network/host unreachable, connection dropped, timeout."""


class ADTAuthenticationError(ADTError):
    """401/403 — bad credentials, or the user lacks S_DEVELOP/ADT
    authorization for the requested object."""


class ADTNotFoundError(ADTError):
    """404 — the requested object doesn't exist, or (just as likely, per
    docs/adt_rfc_integration_plan.md's own findings) the ADT service node
    itself was never activated in SICF."""


class ADTResponseError(ADTError):
    """Any other non-2xx response, or a response we couldn't parse as
    expected. Carries the original status code for callers that want it."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def translate_httpx_exception(exc: Exception) -> ADTError:
    """Map an httpx exception (or a manually-raised one from client.py for
    a non-2xx status) to the app-level hierarchy above. httpx.TransportError
    is the base class for every network/timeout/protocol-level failure
    (ConnectError, ReadTimeout, ConnectTimeout, NetworkError, ...)."""
    if isinstance(exc, httpx.TransportError):
        return ADTConnectionError(str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return ADTAuthenticationError(f"{status}: {exc.response.text[:500]}")
        if status == 404:
            return ADTNotFoundError(f"404: {exc.response.text[:500]}")
        return ADTResponseError(f"{status}: {exc.response.text[:500]}", status_code=status)
    return ADTError(str(exc))
