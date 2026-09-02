"""MCPServer instance (mcp SDK >=2.0 — this class was named FastMCP in
mcp<2.0; both share the same @tool()/Context/lifespan surface). Construction
requires no SAP connectivity — the ConnectionPool connects lazily on first
real use, so `mcp dev` can list tools and validate their schemas with zero
SAP access. AppSettings() does require connection *parameters* to be
configured (see .env.example), even if they're placeholders that are never
actually reached.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import anyio
from mcp.server.mcpserver import MCPServer

from rfc_mcp.adt.client import ADTClient
from rfc_mcp.config import AppSettings
from rfc_mcp.discovery.catalog import FunctionCatalog
from rfc_mcp.execution.invoker import ExecutionInvoker
from rfc_mcp.execution.policy import ExecutionPolicy
from rfc_mcp.execution.result_transform import ResultLimitPolicy
from rfc_mcp.logging_config import configure_logging
from rfc_mcp.sap.connection import ConnectionPool, PooledCaller


@dataclass
class AppContext:
    pool: ConnectionPool
    catalog: FunctionCatalog
    invoker: ExecutionInvoker
    adt_client: ADTClient | None


@asynccontextmanager
async def app_lifespan(server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
    settings = AppSettings()
    configure_logging(settings.log_level)

    pool = ConnectionPool(settings.sap)
    catalog = FunctionCatalog(
        PooledCaller(pool),
        cache_ttl_seconds=settings.discovery_cache_ttl_seconds,
        structure_resolution_max_depth=settings.structure_resolution_max_depth,
    )
    policy = ExecutionPolicy(settings.policy)
    invoker = ExecutionInvoker(
        pool,
        catalog,
        policy,
        transaction_ttl_seconds=settings.transaction_ttl_seconds,
        result_limits=ResultLimitPolicy(
            max_table_rows=settings.result.max_table_rows,
            max_serialized_bytes=settings.result.max_serialized_bytes,
        ),
    )
    # Optional: None unless RFC_MCP_ADT_ENABLED=true. read_abap_source
    # doesn't need this to be set — it falls back to RFC automatically when
    # it's None — see docs/adt_rfc_integration_plan.md.
    adt_client = ADTClient(settings.adt) if settings.adt.enabled else None

    try:
        yield AppContext(pool=pool, catalog=catalog, invoker=invoker, adt_client=adt_client)
    finally:
        await anyio.to_thread.run_sync(invoker.close)
        await anyio.to_thread.run_sync(pool.close_all)
        if adt_client is not None:
            adt_client.close()


# This server has two transports internally (RFC and ADT) but deliberately
# only ONE of them is a caller-facing choice: call_rfc_function is for
# executing business functions/BAPIs — genuine intent only the caller knows
# (read vs. write, which function). Reading ABAP source has no equivalent
# ambiguity, so read_abap_source hides the transport choice entirely: it
# tries ADT when configured and falls back to RFC automatically, including
# on a live ADT failure, not just when disabled. Nothing here relies on a
# calling agent reading and correctly following prose guidance to pick the
# right tool — there is only one tool for this job. See
# docs/adt_rfc_integration_plan.md for the full rationale.
_INSTRUCTIONS = """\
call_rfc_function (with search_rfc_functions / get_rfc_function_interface
to discover what to call, and commit_rfc_transaction / rollback_rfc_transaction
for BAPIs that stage changes) is for EXECUTING business functions — calling
BAPIs, reading or writing business data. mode="read" vs "write" reflects
your actual intent; only you know which one is correct for a given call. A
write returns a transaction_id: reuse it for related writes, then pass it to
commit_rfc_transaction or rollback_rfc_transaction.

read_abap_source is for reading ABAP source code (of a program, class, or
function module) — it automatically uses ADT when available and falls back
to RFC transparently otherwise. You never need to choose a transport or
handle an "ADT not enabled" error yourself; that's handled internally.
"""

mcp: MCPServer[AppContext] = MCPServer(
    "sap-rfc-gateway", instructions=_INSTRUCTIONS, lifespan=app_lifespan
)

# Imported for @mcp.tool() registration side effects.
from rfc_mcp.mcp import (  # noqa: E402, F401
    tools_discovery,
    tools_execution,
    tools_source,
)
