"""Tool registration/schema tests. Requires the `mcp` package but not
pyrfc/SDK — importing rfc_mcp.mcp.server only registers tools via
decorators; the SAP connection pool is built lazily inside app_lifespan,
which these tests never trigger.

FastMCP's exact list_tools()/inputSchema surface should be reconfirmed
against the installed `mcp` SDK version (flagged as an open risk in
docs/architecture.md) — this is best-effort scaffolding.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")


async def test_all_tools_registered():
    from rfc_mcp.mcp.server import mcp

    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "search_rfc_functions",
        "get_rfc_function_interface",
        "call_rfc_function",
        "commit_rfc_transaction",
        "rollback_rfc_transaction",
        "read_abap_source",
    }


async def test_call_rfc_function_schema_has_expected_fields():
    from rfc_mcp.mcp.server import mcp

    tools = await mcp.list_tools()
    call_tool = next(t for t in tools if t.name == "call_rfc_function")
    properties = call_tool.input_schema["properties"]
    assert "function_name" in properties
    assert "parameters" in properties
    assert "mode" in properties
    assert "transaction_id" in properties


async def test_transaction_tools_require_transaction_id():
    from rfc_mcp.mcp.server import mcp

    tools = await mcp.list_tools()
    for name in ("commit_rfc_transaction", "rollback_rfc_transaction"):
        tool = next(t for t in tools if t.name == name)
        assert "transaction_id" in tool.input_schema["required"]


async def test_tool_annotations_describe_risk():
    from rfc_mcp.mcp.server import mcp

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    for name in (
        "search_rfc_functions",
        "get_rfc_function_interface",
        "read_abap_source",
    ):
        assert tools[name].annotations.read_only_hint is True
    for name in (
        "call_rfc_function",
        "commit_rfc_transaction",
        "rollback_rfc_transaction",
    ):
        assert tools[name].annotations.read_only_hint is False
        assert tools[name].annotations.destructive_hint is True


async def test_read_abap_source_schema_has_expected_fields():
    from rfc_mcp.mcp.server import mcp

    tools = await mcp.list_tools()
    source_tool = next(t for t in tools if t.name == "read_abap_source")
    properties = source_tool.input_schema["properties"]
    assert "object_type" in properties
    assert "object_name" in properties
    assert "function_group" in properties
