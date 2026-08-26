"""Discovery-facing MCP tools: search + interface introspection. These are
the entry points an agent is expected to call before call_rfc_function.
"""

from __future__ import annotations

from typing import Annotated, Any

import anyio
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from rfc_mcp.discovery.models import FunctionInterface, FunctionSummary
from rfc_mcp.mcp.server import AppContext, mcp


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
async def search_rfc_functions(
    ctx: Context[AppContext, Any],
    pattern: Annotated[
        str,
        Field(
            description="Function module name pattern, supports '*' wildcards, e.g. 'BAPI_CUSTOMER_*'."
        ),
    ],
    group: Annotated[
        str | None,
        Field(description="Optional function group to restrict the search to."),
    ] = None,
    limit: Annotated[
        int, Field(description="Maximum number of matching functions to return.")
    ] = 50,
) -> list[FunctionSummary]:
    """Search SAP for remote-enabled function modules (BAPIs/RFCs) by name
    pattern (supports '*' wildcards, e.g. 'BAPI_CUSTOMER_*'). Call this
    first to discover available functions before get_rfc_function_interface
    or call_rfc_function.
    """
    app = ctx.request_context.lifespan_context
    return await anyio.to_thread.run_sync(app.catalog.search, pattern, group, limit)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
async def get_rfc_function_interface(
    ctx: Context[AppContext, Any],
    function_name: Annotated[
        str, Field(description="Exact name of the function module to introspect.")
    ],
) -> FunctionInterface:
    """Return the full IMPORT/EXPORT/TABLES/CHANGING parameter interface
    (including resolved structure fields) and documented exceptions for a
    function module. Always call this before call_rfc_function to know
    exactly what parameters are required and how they're shaped.
    """
    app = ctx.request_context.lifespan_context
    return await anyio.to_thread.run_sync(app.catalog.get_interface, function_name)
