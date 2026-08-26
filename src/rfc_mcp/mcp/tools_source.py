"""Unified ABAP source-reading tool. Deliberately a SINGLE tool rather than
separate ADT/RFC ones: reading source has one clearly-best answer whenever
ADT is available, and a well-defined fallback when it isn't — there is no
genuine intent decision here for a calling agent to make (unlike e.g.
mode="read" vs "write" on call_rfc_function, which reflects real caller
intent only the caller knows). So the choice is removed rather than merely
guided: this tool tries ADT first when configured, falls back to RFC
automatically on ANY ADT failure (not just "not configured" — a flaky/
misconfigured ADT service should degrade gracefully, not block the read),
and only raises if both paths fail. See docs/adt_rfc_integration_plan.md.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from rfc_mcp.adt.client import ADTClient
from rfc_mcp.adt.exceptions import ADTError
from rfc_mcp.execution import source_reader
from rfc_mcp.execution.invoker import ExecutionInvoker
from rfc_mcp.mcp.schemas import AbapSourceOutput
from rfc_mcp.mcp.server import AppContext, mcp

logger = logging.getLogger("rfc_mcp.mcp.tools_source")


def _read_via_adt(
    adt_client: ADTClient,
    object_type: str,
    object_name: str,
    function_group: str | None,
) -> str:
    if object_type == "program":
        return adt_client.get_program_source(object_name)
    if object_type == "class":
        return adt_client.get_class_source(object_name)
    assert function_group  # validated by caller
    return adt_client.get_function_module_source(function_group, object_name)


def _read_via_rfc(
    invoker: ExecutionInvoker,
    object_type: str,
    object_name: str,
    function_group: str | None,
) -> str:
    if object_type == "program":
        return source_reader.read_program_source(invoker, object_name)
    if object_type == "class":
        return source_reader.read_class_source(invoker, object_name)
    assert function_group  # validated by caller
    return source_reader.read_function_module_source(invoker, object_name)


def _read_source(
    app: AppContext,
    object_type: str,
    object_name: str,
    function_group: str | None,
) -> tuple[str, Literal["adt", "rfc"]]:
    """Synchronous — called via anyio.to_thread.run_sync as one unit, so a
    multi-call class read (RPY_PROGRAM_READ x N) doesn't pay thread-offload
    overhead per include. Returns (source, via)."""
    if app.adt_client is not None:
        try:
            return _read_via_adt(app.adt_client, object_type, object_name, function_group), "adt"
        except ADTError as exc:
            logger.warning(
                "ADT read failed for %s %s (%s: %s), falling back to RFC",
                object_type,
                object_name,
                type(exc).__name__,
                exc,
            )
    return _read_via_rfc(app.invoker, object_type, object_name, function_group), "rfc"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
async def read_abap_source(
    ctx: Context[AppContext, Any],
    object_type: Annotated[
        Literal["program", "class", "function_module"],
        Field(description="Kind of ABAP object to read source for."),
    ],
    object_name: Annotated[
        str,
        Field(description="Name of the program, class, or function module to read source for."),
    ],
    function_group: Annotated[
        str | None,
        Field(
            description="Function group the function module belongs to. Required when object_type='function_module', ignored otherwise."
        ),
    ] = None,
) -> AbapSourceOutput:
    """Read the full ABAP source of a program, class, or function module.
    Automatically uses ADT (one call, most reliable — especially for
    classes, which need several RFC calls otherwise) when it's enabled and
    reachable, and transparently falls back to RFC (RPY_PROGRAM_READ /
    RPY_FUNCTIONMODULE_READ) otherwise — including on a live ADT failure,
    not just when it's disabled. You never need to choose the transport
    yourself; check the returned `via` field if you want to know which one
    actually served the read. function_group is required when
    object_type='function_module'.
    """
    app = ctx.request_context.lifespan_context

    if object_type == "function_module" and not function_group:
        raise ValueError("function_group is required when object_type='function_module'")

    source, via = await anyio.to_thread.run_sync(
        _read_source, app, object_type, object_name, function_group
    )

    return AbapSourceOutput(
        object_type=object_type,
        object_name=object_name,
        function_group=function_group,
        source=source,
        via=via,
    )
