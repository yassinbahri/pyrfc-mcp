"""pyrfc-dependent: only runs once pyrfc is actually importable (pinned
Python 3.11 venv + SDK, see docs/setup.md). Exact pyrfc exception
constructor signatures should be verified against the installed version —
this is best-effort scaffolding, flagged in docs/architecture.md's open
risks.
"""

from __future__ import annotations

import pytest

pyrfc = pytest.importorskip("pyrfc")

from rfc_mcp.sap.exceptions import (
    SAPApplicationError,
    SAPCommunicationError,
    SAPLogonError,
    SAPRuntimeError,
    translate_pyrfc_exception,
)


def test_translate_logon_error():
    translated = translate_pyrfc_exception(pyrfc.LogonError("bad credentials"))
    assert isinstance(translated, SAPLogonError)


def test_translate_communication_error():
    translated = translate_pyrfc_exception(pyrfc.CommunicationError("host unreachable"))
    assert isinstance(translated, SAPCommunicationError)


def test_translate_abap_application_error():
    exc = pyrfc.ABAPApplicationError(key="CUSTOMER_NOT_FOUND", message="Customer 123 not found")
    translated = translate_pyrfc_exception(exc)
    assert isinstance(translated, SAPApplicationError)
    assert translated.key == "CUSTOMER_NOT_FOUND"


def test_translate_abap_runtime_error():
    translated = translate_pyrfc_exception(pyrfc.ABAPRuntimeError("dump occurred"))
    assert isinstance(translated, SAPRuntimeError)
