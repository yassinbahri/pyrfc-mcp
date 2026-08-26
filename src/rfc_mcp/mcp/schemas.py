"""Pydantic I/O models for MCP tools that aren't already covered by
discovery/models.py (FunctionSummary and FunctionInterface are reused
directly as tool return types there).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class CallFunctionOutput(BaseModel):
    function_name: str
    result: dict[str, Any]
    transaction_id: str | None = None


class TransactionControlOutput(BaseModel):
    action: Literal["commit", "rollback"]
    transaction_id: str
    result: dict[str, Any]


class AbapSourceOutput(BaseModel):
    object_type: Literal["program", "class", "function_module"]
    object_name: str
    function_group: str | None = None
    source: str
    # Which transport actually served this read — informational only.
    # Callers never need to choose this themselves; read_abap_source picks
    # the best available option automatically (ADT if enabled and
    # reachable, RFC otherwise).
    via: Literal["adt", "rfc"]
