"""ADT HTTP client. `import httpx` stays confined to this module and
exceptions.py (mirroring how `import pyrfc` is confined to sap/connection.py)
so the rest of the package doesn't need to know which transport backs a
given capability.

Read-only by design (see config.ADTConnectionSettings' docstring) — every
method here is a GET. There is deliberately no write/activate capability.
"""

from __future__ import annotations

import logging
import time
from typing import Self
from urllib.parse import quote

import httpx

from rfc_mcp.adt.exceptions import ADTNotConfiguredError, translate_httpx_exception
from rfc_mcp.config import ADTConnectionSettings

logger = logging.getLogger("rfc_mcp.adt.client")

# ADT's source-read endpoints always return the raw ABAP source as
# text/plain, regardless of object type — this is the one Accept header
# every one of them wants.
_SOURCE_ACCEPT = "text/plain"


def _program_source_uri(program_name: str) -> str:
    return f"/sap/bc/adt/programs/programs/{quote(program_name)}/source/main"


def _class_source_uri(class_name: str) -> str:
    return f"/sap/bc/adt/oo/classes/{quote(class_name)}/source/main"


def _function_module_source_uri(function_group: str, function_module: str) -> str:
    return (
        f"/sap/bc/adt/functions/groups/{quote(function_group)}"
        f"/fmodules/{quote(function_module)}/source/main"
    )


class ADTClient:
    """Thin wrapper over a persistent httpx.Client. Unlike pyrfc.Connection,
    a single httpx.Client already pools/reuses underlying TCP connections
    safely for concurrent use, so there's no need for the bounded
    checkout/checkin pool ConnectionPool implements for RFC."""

    def __init__(
        self, settings: ADTConnectionSettings, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        """transport is test-only injection (httpx.MockTransport) — normal
        callers never pass it, and httpx.Client builds its own real
        transport when omitted."""
        if not settings.enabled:
            raise ADTNotConfiguredError(
                "ADT is not enabled (RFC_MCP_ADT_ENABLED is not true). See "
                "docs/adt_rfc_integration_plan.md."
            )
        self._settings = settings
        assert settings.host and settings.user and settings.passwd  # enforced by settings validator
        self._client = httpx.Client(
            base_url=settings.base_url,
            auth=(settings.user, settings.passwd.get_secret_value()),
            verify=settings.verify_ssl,
            timeout=settings.timeout_seconds,
            params={"sap-client": settings.client} if settings.client else None,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _get_with_retry(self, uri: str, *, accept: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                response = self._client.get(uri, headers={"Accept": accept})
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                # Retrying a 4xx wastes time — it'll fail the same way every
                # time. Only retry transport-level failures and 5xx.
                if exc.response.status_code < 500:
                    raise translate_httpx_exception(exc) from exc
                last_exc = exc
            except httpx.TransportError as exc:
                last_exc = exc
            if attempt < self._settings.max_retries:
                time.sleep(self._settings.backoff_base_seconds * (2**attempt))
        assert last_exc is not None
        raise translate_httpx_exception(last_exc) from last_exc

    def get_program_source(self, program_name: str) -> str:
        return self._get_with_retry(_program_source_uri(program_name), accept=_SOURCE_ACCEPT).text

    def get_class_source(self, class_name: str) -> str:
        """Unlike RFC (RPY_PROGRAM_READ against a manually-guessed
        class-pool include name, then walking WITH_INCLUDELIST for the
        method includes — see the deep-dive report this project produced
        manually via that route), ADT returns a class's whole source,
        methods included, in this one call."""
        return self._get_with_retry(_class_source_uri(class_name), accept=_SOURCE_ACCEPT).text

    def get_function_module_source(self, function_group: str, function_module: str) -> str:
        return self._get_with_retry(
            _function_module_source_uri(function_group, function_module), accept=_SOURCE_ACCEPT
        ).text
