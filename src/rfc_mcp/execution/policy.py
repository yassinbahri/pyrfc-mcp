"""Execution-time authorization. RFC has no universal "this function is safe
to read" flag, so this is necessarily a config-driven allow/deny
classification (see rfc_mcp.config.PolicySettings), fail-closed: anything not
explicitly allowed is blocked.
"""

from __future__ import annotations

import logging
from typing import Any

from rfc_mcp.config import PolicyMode, PolicySettings

logger = logging.getLogger("rfc_mcp.execution.policy")

# Parameter name RFC_READ_TABLE and its known clones use for the table being
# read. See config.GENERIC_TABLE_READER_FUNCTIONS.
GENERIC_TABLE_READER_PARAM = "QUERY_TABLE"


class PolicyDeniedError(Exception):
    def __init__(self, function_name: str, mode: str, reason: str) -> None:
        super().__init__(f"Call to {function_name!r} in mode={mode!r} denied: {reason}")
        self.function_name = function_name
        self.mode = mode
        self.reason = reason


class ExecutionPolicy:
    def __init__(self, settings: PolicySettings) -> None:
        self._settings = settings

    def authorize(
        self, function_name: str, mode: str, parameters: dict[str, Any] | None = None
    ) -> None:
        """Every decision this method makes is logged — this is the single
        security-relevant choke point every RFC call passes through, and
        (before this) left no record anywhere of what was allowed, denied,
        or attempted. Never logs parameter values in bulk (could carry
        business-sensitive data) — the one deliberate exception is the
        target table name for generic table-reader calls, since that's
        exactly the audit signal the table_deny_patterns guard exists for."""
        table_name = self._generic_table_reader_target(function_name, parameters or {})
        try:
            self._authorize_unlogged(function_name, mode, table_name)
        except PolicyDeniedError as exc:
            logger.warning(
                "DENIED function=%s mode=%s table=%s reason=%s",
                function_name,
                mode,
                table_name,
                exc.reason,
            )
            raise
        logger.info("ALLOWED function=%s mode=%s table=%s", function_name, mode, table_name)

    def _authorize_unlogged(self, function_name: str, mode: str, table_name: str | None) -> None:
        if table_name is not None and self._settings.is_table_denied(table_name):
            raise PolicyDeniedError(
                function_name,
                mode,
                f"target table {table_name!r} matches table_deny_patterns (generic table-reader guard)",
            )
        if mode == "read":
            if not self._settings.is_read_allowed(function_name):
                raise PolicyDeniedError(
                    function_name, mode, "not in read_allow_patterns, or explicitly denied"
                )
            return
        if mode == "write":
            if self._settings.mode is not PolicyMode.READ_WRITE:
                raise PolicyDeniedError(function_name, mode, "server policy mode is read_only")
            if not self._settings.is_write_allowed(function_name):
                raise PolicyDeniedError(
                    function_name, mode, "not in write_allow_patterns, or explicitly denied"
                )
            return
        raise ValueError(f"Unknown mode: {mode!r}")

    def _generic_table_reader_target(
        self, function_name: str, parameters: dict[str, Any]
    ) -> str | None:
        """Second, independent guard for functions like RFC_READ_TABLE that
        read whatever table a caller-supplied parameter names — deny_patterns
        can't catch this since the function's own name never matches a
        mutating-verb pattern. Returns the target table name if this call is
        a generic table read with a table specified, else None."""
        if not self._settings.is_generic_table_reader(function_name):
            return None
        provided_upper = {k.upper(): v for k, v in parameters.items()}
        table_name = provided_upper.get(GENERIC_TABLE_READER_PARAM)
        return str(table_name) if table_name else None

    def authorize_transaction_control(self) -> None:
        """Gate commit_rfc_transaction / rollback_rfc_transaction: only
        meaningful when the server is in read_write mode at all."""
        if self._settings.mode is not PolicyMode.READ_WRITE:
            logger.warning(
                "DENIED <transaction-control> mode=write reason=server policy mode is read_only"
            )
            raise PolicyDeniedError(
                "<transaction-control>", "write", "server policy mode is read_only"
            )
        logger.info("ALLOWED <transaction-control> mode=write")
