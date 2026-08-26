from __future__ import annotations

from dataclasses import dataclass

from rfc_mcp.sap.connection import ConnectionPool
from rfc_mcp.sap.exceptions import SAPError


@dataclass
class HealthCheckResult:
    ok: bool
    detail: str
    exc: SAPError | None = None


def check_connectivity(pool: ConnectionPool) -> HealthCheckResult:
    """Acquire a connection and ping it. Does not raise — failures are
    reported in the result so callers (smoke tests, health tools) can
    distinguish logon vs. communication vs. other errors from `detail`, or
    from the `exc` instance directly (e.g. via isinstance checks).
    """
    try:
        with pool.acquire() as conn:
            conn.ping()
        return HealthCheckResult(ok=True, detail="Connected and ping succeeded.")
    except SAPError as exc:
        return HealthCheckResult(ok=False, detail=f"{type(exc).__name__}: {exc}", exc=exc)
