from __future__ import annotations

from contextlib import contextmanager

from rfc_mcp.config import PolicyMode, PolicySettings
from rfc_mcp.discovery.catalog import FunctionCatalog
from rfc_mcp.execution import source_reader
from rfc_mcp.execution.invoker import ExecutionInvoker
from rfc_mcp.execution.policy import ExecutionPolicy
from tests.fakes.fake_pyrfc import FakeConnection
from tests.fakes.sample_data import function_interface_responder


class _FakePool:
    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    @contextmanager
    def acquire(self):
        yield self._conn


def _invoker(responses: dict) -> ExecutionInvoker:
    all_responses = {"RFC_GET_FUNCTION_INTERFACE": function_interface_responder, **responses}
    caller = FakeConnection(responses=all_responses)
    catalog = FunctionCatalog(caller)
    policy = ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))
    return ExecutionInvoker(_FakePool(caller), catalog, policy)


def test_read_program_source_joins_lines():
    def rpy_program_read(params):
        assert params["PROGRAM_NAME"] == "ZFOO"
        return {"SOURCE_EXTENDED": [{"LINE": "REPORT zfoo."}, {"LINE": "WRITE 'hi'."}]}

    invoker = _invoker({"RPY_PROGRAM_READ": rpy_program_read})
    assert source_reader.read_program_source(invoker, "ZFOO") == "REPORT zfoo.\nWRITE 'hi'."


def test_read_function_module_source_joins_lines():
    def rpy_fm_read(params):
        assert params["FUNCTIONNAME"] == "Z_FOO"
        return {"SOURCE": [{"LINE": "FUNCTION z_foo."}, {"LINE": "ENDFUNCTION."}]}

    invoker = _invoker({"RPY_FUNCTIONMODULE_READ": rpy_fm_read})
    assert (
        source_reader.read_function_module_source(invoker, "Z_FOO")
        == "FUNCTION z_foo.\nENDFUNCTION."
    )


def test_read_class_source_pads_class_name_to_30_chars_with_equals():
    seen_program_names = []

    def rpy_program_read(params):
        seen_program_names.append(params["PROGRAM_NAME"])
        if params["PROGRAM_NAME"] == "ZCL_SHORT" + "=" * 21 + "CP":
            assert params.get("WITH_INCLUDELIST") == "X"
            return {"INCLUDE_TAB": [{"INCLNAME": "ZCL_SHORT" + "=" * 21 + "CU"}]}
        return {"SOURCE_EXTENDED": [{"LINE": "PUBLIC SECTION."}]}

    invoker = _invoker({"RPY_PROGRAM_READ": rpy_program_read})
    source = source_reader.read_class_source(invoker, "ZCL_SHORT")

    # "ZCL_SHORT" is 9 chars; padded to 30 with '=' is 21 '=' characters.
    assert "ZCL_SHORT" + "=" * 21 + "CP" in seen_program_names
    assert "ZCL_SHORT" + "=" * 21 + "CU" in seen_program_names
    assert "PUBLIC SECTION." in source
    assert "ZCL_SHORT" + "=" * 21 + "CU" in source  # include header marker present


def test_read_class_source_needs_no_padding_when_name_is_30_chars_or_longer():
    long_name = "ZCL_ALREADY_THIRTY_CHARS_LONGX"  # exactly 30 chars
    assert len(long_name) == 30
    seen_program_names = []

    def rpy_program_read(params):
        seen_program_names.append(params["PROGRAM_NAME"])
        return {"INCLUDE_TAB": []}

    invoker = _invoker({"RPY_PROGRAM_READ": rpy_program_read})
    source_reader.read_class_source(invoker, long_name)

    assert seen_program_names == [long_name + "CP"]  # ljust is a no-op here


def test_read_class_source_falls_back_to_cp_skeleton_when_no_includes_found():
    def rpy_program_read(params):
        return {"INCLUDE_TAB": [], "SOURCE_EXTENDED": [{"LINE": "CLASS-POOL."}]}

    invoker = _invoker({"RPY_PROGRAM_READ": rpy_program_read})
    assert source_reader.read_class_source(invoker, "ZCL_EMPTY") == "CLASS-POOL."


def test_read_class_source_skips_unreadable_include_but_keeps_the_rest():
    # Found live against a real (newer-release) SAP system: WITH_INCLUDELIST
    # can list an include that RPY_PROGRAM_READ itself can't return source
    # for (there, a "CCAU" suffix not seen on older releases). One bad
    # include must not fail the whole class read.
    cu_name = "ZCL_PARTIAL" + "=" * 19 + "CU"
    bad_name = "ZCL_PARTIAL" + "=" * 17 + "CCAU"

    def rpy_program_read(params):
        name = params["PROGRAM_NAME"]
        if name == "ZCL_PARTIAL" + "=" * 19 + "CP":
            return {"INCLUDE_TAB": [{"INCLNAME": cu_name}, {"INCLNAME": bad_name}]}
        if name == bad_name:
            raise RuntimeError("ID:XI Type:E Number:004 " + bad_name)
        return {"SOURCE_EXTENDED": [{"LINE": "PUBLIC SECTION."}]}

    invoker = _invoker({"RPY_PROGRAM_READ": rpy_program_read})
    source = source_reader.read_class_source(invoker, "ZCL_PARTIAL")

    assert "PUBLIC SECTION." in source
    assert bad_name in source
    assert "unreadable" in source


def test_read_class_source_reads_every_discovered_include():
    includes = {
        "ZCL_MULTI" + "=" * 21 + "CU": "PUBLIC SECTION.",
        "ZCL_MULTI" + "=" * 21 + "CI": "PRIVATE SECTION.",
        "ZCL_MULTI" + "=" * 21 + "CM001": "METHOD foo.\nENDMETHOD.",
    }

    def rpy_program_read(params):
        name = params["PROGRAM_NAME"]
        if name == "ZCL_MULTI" + "=" * 21 + "CP":
            return {"INCLUDE_TAB": [{"INCLNAME": n} for n in includes]}
        return {"SOURCE_EXTENDED": [{"LINE": includes[name]}]}

    invoker = _invoker({"RPY_PROGRAM_READ": rpy_program_read})
    source = source_reader.read_class_source(invoker, "ZCL_MULTI")

    for expected_line in includes.values():
        assert expected_line in source
