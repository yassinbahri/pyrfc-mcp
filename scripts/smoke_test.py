"""Manual smoke test — run once real SAP credentials exist (see .env):

    python scripts/smoke_test.py

Validates connectivity, then does a harmless real read (discovery +
execution) against SAP's standard, always-available, side-effect-free
connectivity test module STFC_CONNECTION. Prints diagnostics distinguishing
logon vs. communication vs. other failures.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rfc_mcp.config import AppSettings
from rfc_mcp.discovery.catalog import FunctionCatalog
from rfc_mcp.execution.invoker import ExecutionInvoker
from rfc_mcp.execution.policy import ExecutionPolicy
from rfc_mcp.logging_config import configure_logging
from rfc_mcp.sap.connection import ConnectionPool, PooledCaller
from rfc_mcp.sap.exceptions import (
    SAPCommunicationError,
    SAPError,
    SAPLogonError,
    SAPUnavailableError,
)
from rfc_mcp.sap.health import check_connectivity


def _exit_code_for(exc: SAPError) -> int:
    if isinstance(exc, SAPUnavailableError):
        return 2
    if isinstance(exc, SAPLogonError):
        return 3
    if isinstance(exc, SAPCommunicationError):
        return 4
    return 5


def main() -> int:
    settings = AppSettings()
    configure_logging(settings.log_level)

    pool = ConnectionPool(settings.sap)
    invoker: ExecutionInvoker | None = None
    try:
        print("1. Checking connectivity...")
        health = check_connectivity(pool)
        if not health.ok:
            print(f"   FAILED: {health.detail}")
            return _exit_code_for(health.exc) if health.exc is not None else 1
        print(f"   OK: {health.detail}")

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
        )

        print("2. Introspecting STFC_CONNECTION interface...")
        interface = catalog.get_interface("STFC_CONNECTION")
        print(
            f"   {len(interface.parameters)} parameter(s): {[p.name for p in interface.parameters]}"
        )

        print("3. Calling STFC_CONNECTION (side-effect-free echo test)...")
        result = invoker.call("STFC_CONNECTION", {"REQUTEXT": "rfc-mcp smoke test"}, mode="read")
        print(f"   Result: {result}")

        print("\nSmoke test passed.")
        return 0
    except SAPUnavailableError as exc:
        print(f"pyrfc/SDK not available: {exc}\nSee docs/setup.md.")
        return _exit_code_for(exc)
    except SAPLogonError as exc:
        print(f"Logon failed (check credentials): {exc}")
        return _exit_code_for(exc)
    except SAPCommunicationError as exc:
        print(f"Communication failed (check host/network): {exc}")
        return _exit_code_for(exc)
    except SAPError as exc:
        print(f"SAP error: {type(exc).__name__}: {exc}")
        return _exit_code_for(exc)
    finally:
        if invoker is not None:
            invoker.close()
        pool.close_all()


if __name__ == "__main__":
    raise SystemExit(main())
