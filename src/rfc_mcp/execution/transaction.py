"""BAPI commit/rollback. Many SAP write BAPIs stage changes in the current
LUW and require a separate BAPI_TRANSACTION_COMMIT to persist — this server
never calls these implicitly from call_rfc_function; only the dedicated
commit_rfc_transaction / rollback_rfc_transaction MCP tools trigger them.
"""

from __future__ import annotations

from typing import Any

from rfc_mcp.sap.caller import RfcCaller


def commit(caller: RfcCaller, wait: bool = False) -> dict[str, Any]:
    return caller.call("BAPI_TRANSACTION_COMMIT", WAIT="X" if wait else "")


def rollback(caller: RfcCaller) -> dict[str, Any]:
    return caller.call("BAPI_TRANSACTION_ROLLBACK")
