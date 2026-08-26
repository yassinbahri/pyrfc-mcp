"""Tests for the read_abap_source fallback DECISION itself — the actual
point of this tool's existence: never require a calling agent to choose
between ADT and RFC, or to notice/handle an ADT failure itself.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")

from rfc_mcp.adt.exceptions import ADTConnectionError
from rfc_mcp.mcp.tools_source import _read_source


class _FakeAdtClient:
    def __init__(self, *, program_source=None, class_source=None, fm_source=None, raises=None):
        self._program_source = program_source
        self._class_source = class_source
        self._fm_source = fm_source
        self._raises = raises
        self.calls: list[str] = []

    def get_program_source(self, name):
        self.calls.append(f"program:{name}")
        if self._raises:
            raise self._raises
        return self._program_source

    def get_class_source(self, name):
        self.calls.append(f"class:{name}")
        if self._raises:
            raise self._raises
        return self._class_source

    def get_function_module_source(self, group, name):
        self.calls.append(f"fm:{group}/{name}")
        if self._raises:
            raise self._raises
        return self._fm_source


class _FakeInvoker:
    """Stands in for the RFC fallback path without needing a real
    ExecutionInvoker/FunctionCatalog — source_reader.py's own logic is
    tested separately in test_source_reader.py."""

    def __init__(self):
        self.calls: list[tuple] = []

    def call(self, function_name, parameters, mode):
        self.calls.append((function_name, parameters, mode))
        if function_name == "RPY_PROGRAM_READ":
            return {"SOURCE_EXTENDED": [{"LINE": "REPORT zfoo. (via rfc)"}]}
        if function_name == "RPY_FUNCTIONMODULE_READ":
            return {"SOURCE": [{"LINE": "FUNCTION z_foo. (via rfc)"}]}
        raise AssertionError(f"unexpected function {function_name}")


def test_uses_adt_when_configured_and_working():
    adt = _FakeAdtClient(program_source="REPORT zfoo. (via adt)")
    app = SimpleNamespace(adt_client=adt, invoker=_FakeInvoker())

    source, via = _read_source(app, "program", "ZFOO", None)

    assert via == "adt"
    assert source == "REPORT zfoo. (via adt)"
    assert adt.calls == ["program:ZFOO"]


def test_falls_back_to_rfc_when_adt_not_configured():
    app = SimpleNamespace(adt_client=None, invoker=_FakeInvoker())

    source, via = _read_source(app, "program", "ZFOO", None)

    assert via == "rfc"
    assert "via rfc" in source


def test_falls_back_to_rfc_when_adt_configured_but_fails():
    adt = _FakeAdtClient(raises=ADTConnectionError("connection refused"))
    invoker = _FakeInvoker()
    app = SimpleNamespace(adt_client=adt, invoker=invoker)

    source, via = _read_source(app, "program", "ZFOO", None)

    # ADT was genuinely tried (not skipped), and its failure didn't
    # propagate — the caller gets a working answer either way.
    assert adt.calls == ["program:ZFOO"]
    assert via == "rfc"
    assert "via rfc" in source


def test_function_module_routes_to_correct_method_on_both_transports():
    adt = _FakeAdtClient(fm_source="FUNCTION z_foo. (via adt)")
    app = SimpleNamespace(adt_client=adt, invoker=_FakeInvoker())

    _source, via = _read_source(app, "function_module", "Z_FOO", "ZFG")

    assert via == "adt"
    assert adt.calls == ["fm:ZFG/Z_FOO"]

    app_no_adt = SimpleNamespace(adt_client=None, invoker=_FakeInvoker())
    _source, via = _read_source(app_no_adt, "function_module", "Z_FOO", "ZFG")
    assert via == "rfc"
    assert app_no_adt.invoker.calls[0][0] == "RPY_FUNCTIONMODULE_READ"


def test_class_routes_to_get_class_source_on_adt():
    # RFC-side class reading (the include-walking) is tested thoroughly in
    # test_source_reader.py; this only checks the routing decision itself.
    adt = _FakeAdtClient(class_source="CLASS zcl_foo. (via adt)")
    app = SimpleNamespace(adt_client=adt, invoker=_FakeInvoker())

    _source, via = _read_source(app, "class", "ZCL_FOO", None)

    assert via == "adt"
    assert adt.calls == ["class:ZCL_FOO"]
