"""App-level exception hierarchy, decoupled from pyrfc's own exception
classes so the rest of the codebase never needs `import pyrfc` directly.
`translate_pyrfc_exception` is the only place pyrfc exception types are
referenced, and it imports pyrfc lazily.
"""

from __future__ import annotations


class SAPError(Exception):
    """Base class for all SAP-related errors raised by this server."""


class SAPUnavailableError(SAPError):
    """pyrfc is not installed or the SAP NW RFC SDK failed to load."""


class SAPPoolTimeoutError(SAPUnavailableError):
    """No SAP connection became available before the configured timeout."""


class SAPLogonError(SAPError):
    """Authentication/authorization failure (bad credentials, locked user)."""


class SAPCommunicationError(SAPError):
    """Network/host unreachable, connection dropped, timeout."""


class SAPApplicationError(SAPError):
    """An ABAP-level exception was raised by the called function module."""

    def __init__(self, message: str, key: str | None = None) -> None:
        super().__init__(message)
        self.key = key


class SAPRuntimeError(SAPError):
    """An ABAP runtime error (dump) occurred during the call."""


def translate_pyrfc_exception(exc: Exception) -> SAPError:
    """Map a pyrfc exception instance to the app-level hierarchy above.

    Exact pyrfc exception class names/kwargs should be verified against the
    installed pyrfc version (see docs/setup.md) — this defends with getattr
    fallbacks rather than assuming a fixed constructor shape.
    """
    try:
        import pyrfc
    except ImportError:
        return SAPError(str(exc))

    if isinstance(exc, pyrfc.LogonError):
        return SAPLogonError(str(exc))
    if isinstance(exc, pyrfc.CommunicationError):
        return SAPCommunicationError(str(exc))
    if isinstance(exc, pyrfc.ABAPApplicationError):
        key = getattr(exc, "key", None)
        message = getattr(exc, "message", None) or str(exc)
        return SAPApplicationError(message, key=key)
    if isinstance(exc, pyrfc.ABAPRuntimeError):
        return SAPRuntimeError(str(exc))
    # Any other pyrfc error (e.g. RFCLibError/RFCError base classes) falls
    # through to the generic SAPError below.
    return SAPError(str(exc))
