"""Safe, human-readable preflight diagnostics for local installations."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import ValidationError

from rfc_mcp.config import AppSettings, BackendMode, SAPConnectionSettings
from rfc_mcp.demo import DemoConnectionPool
from rfc_mcp.sap.connection import ConnectionManager, ConnectionPool
from rfc_mcp.sap.health import check_connectivity


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    SKIP = "skip"
    FAIL = "fail"


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class DiagnosticReport:
    backend: str
    checks: tuple[DiagnosticCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status is not CheckStatus.FAIL for check in self.checks)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "backend": self.backend,
            "checks": [
                {"name": check.name, "status": check.status.value, "detail": check.detail}
                for check in self.checks
            ],
        }


def _probe_pyrfc() -> None:
    importlib.import_module("pyrfc")


def _configuration_error(exc: ValidationError) -> str:
    """Render validation failures without echoing credential values."""
    problems = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in error["loc"])
        problems.append(f"{location}: {error['msg']}")
    return "; ".join(problems)


def run_diagnostics(
    settings: AppSettings,
    *,
    connect: bool = False,
    pyrfc_probe: Callable[[], None] = _probe_pyrfc,
    pool_factory: Callable[[SAPConnectionSettings], ConnectionManager] = ConnectionPool,
) -> DiagnosticReport:
    """Check configuration and dependencies, contacting SAP only on request."""
    checks = [
        DiagnosticCheck("backend", CheckStatus.PASS, f"Selected {settings.backend.value} backend."),
    ]

    if settings.backend is BackendMode.DEMO:
        checks.extend(
            [
                DiagnosticCheck(
                    "configuration",
                    CheckStatus.PASS,
                    "Demo mode needs no SAP host, credentials, PyRFC, or NW RFC SDK.",
                ),
                DiagnosticCheck(
                    "pyrfc",
                    CheckStatus.SKIP,
                    "Not required by the demo backend.",
                ),
            ]
        )
        pool: ConnectionManager = DemoConnectionPool()
    else:
        try:
            sap_settings = settings.sap_settings()
        except ValidationError as exc:
            checks.append(
                DiagnosticCheck("configuration", CheckStatus.FAIL, _configuration_error(exc))
            )
            return DiagnosticReport(settings.backend.value, tuple(checks))

        addressing = "direct application server" if sap_settings.ashost else "message server"
        checks.append(
            DiagnosticCheck(
                "configuration",
                CheckStatus.PASS,
                f"Valid {addressing} settings; credential values are intentionally hidden.",
            )
        )
        try:
            pyrfc_probe()
        except Exception as exc:
            checks.append(
                DiagnosticCheck(
                    "pyrfc",
                    CheckStatus.FAIL,
                    f"PyRFC or the NW RFC SDK could not be loaded ({type(exc).__name__}).",
                )
            )
            return DiagnosticReport(settings.backend.value, tuple(checks))
        checks.append(
            DiagnosticCheck("pyrfc", CheckStatus.PASS, "PyRFC and its native SDK loaded.")
        )
        pool = pool_factory(sap_settings)

    if settings.policy.read_allow_patterns or settings.backend is BackendMode.DEMO:
        checks.append(
            DiagnosticCheck(
                "read policy", CheckStatus.PASS, "At least one read allow pattern is active."
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                "read policy",
                CheckStatus.WARN,
                "No read allow patterns are configured; all business RFC calls remain denied.",
            )
        )

    if not connect:
        checks.append(
            DiagnosticCheck(
                "connectivity",
                CheckStatus.SKIP,
                "Not attempted. Pass --connect to perform a live ping.",
            )
        )
        return DiagnosticReport(settings.backend.value, tuple(checks))

    result = check_connectivity(pool)
    checks.append(
        DiagnosticCheck(
            "connectivity",
            CheckStatus.PASS if result.ok else CheckStatus.FAIL,
            result.detail,
        )
    )
    pool.close_all()
    return DiagnosticReport(settings.backend.value, tuple(checks))
