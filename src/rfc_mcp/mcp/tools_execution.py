"""Execution-facing MCP tools: call, commit, rollback. call_rfc_function
never auto-commits — commit_rfc_transaction / rollback_rfc_transaction are
separate, explicit tools so an agent can inspect results before persisting.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from rfc_mcp.mcp.schemas import CallFunctionOutput, TransactionControlOutput
from rfc_mcp.mcp.server import AppContext, mcp


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
async def call_rfc_function(
    ctx: Context[AppContext, Any],
    function_name: Annotated[
        str,
        Field(description="Exact name of the RFC-enabled function module to invoke."),
    ],
    parameters: Annotated[
        dict[str, Any],
        Field(
            description="IMPORT/TABLES/CHANGING parameter values, keyed by name as returned by get_rfc_function_interface."
        ),
    ],
    mode: Annotated[
        Literal["read", "write"],
        Field(
            description="Your actual intent for this call: 'read' for non-mutating calls, 'write' if it changes SAP data. Checked against server policy."
        ),
    ] = "read",
    transaction_id: Annotated[
        str | None,
        Field(
            description="For write mode, reuse the opaque transaction_id returned by an earlier write to keep all calls in the same SAP LUW. Omit on the first write and for reads."
        ),
    ] = None,
) -> CallFunctionOutput:
    """Invoke a SAP RFC-enabled function module with JSON parameters. Call
    get_rfc_function_interface first to know what parameters are required.
    mode='write' is required for functions classified as mutating and is
    rejected unless the server's policy explicitly allows writes for that
    function. A write returns a transaction_id tied to its SAP connection;
    reuse it for related writes, then pass it to commit_rfc_transaction or
    rollback_rfc_transaction. Writes are never auto-committed.
    """
    app = ctx.request_context.lifespan_context
    result, active_transaction_id = await anyio.to_thread.run_sync(
        app.invoker.call_transactional,
        function_name,
        parameters,
        mode,
        transaction_id,
    )
    return CallFunctionOutput(
        function_name=function_name,
        result=result,
        transaction_id=active_transaction_id,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
async def commit_rfc_transaction(
    ctx: Context[AppContext, Any],
    transaction_id: Annotated[
        str,
        Field(description="Opaque transaction ID returned by the write call(s) to commit."),
    ],
    wait: Annotated[
        bool,
        Field(
            description="If true, wait for the commit to be confirmed by the update task before returning."
        ),
    ] = False,
) -> TransactionControlOutput:
    """Persist changes staged by prior write call_rfc_function calls in the
    identified SAP transaction (BAPI_TRANSACTION_COMMIT). Only available
    when the server policy mode is read_write.
    """
    app = ctx.request_context.lifespan_context
    result = await anyio.to_thread.run_sync(app.invoker.commit, transaction_id, wait)
    return TransactionControlOutput(action="commit", transaction_id=transaction_id, result=result)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
async def rollback_rfc_transaction(
    ctx: Context[AppContext, Any],
    transaction_id: Annotated[
        str,
        Field(description="Opaque transaction ID returned by the write call(s) to roll back."),
    ],
) -> TransactionControlOutput:
    """Discard changes staged by prior write call_rfc_function calls in the
    identified SAP transaction (BAPI_TRANSACTION_ROLLBACK). Only available
    when the server policy mode is read_write.
    """
    app = ctx.request_context.lifespan_context
    result = await anyio.to_thread.run_sync(app.invoker.rollback, transaction_id)
    return TransactionControlOutput(action="rollback", transaction_id=transaction_id, result=result)
