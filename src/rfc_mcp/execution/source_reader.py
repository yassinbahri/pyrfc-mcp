"""RFC-based ABAP source reading — the fallback path when ADT isn't
available (see docs/adt_rfc_integration_plan.md). Goes through the same
ExecutionInvoker as call_rfc_function, so these calls are subject to the
exact same policy/audit logging as an agent calling RPY_PROGRAM_READ or
RPY_FUNCTIONMODULE_READ directly — nothing here bypasses read_allow_patterns
or the audit trail; PolicyDeniedError propagates normally if an operator has
locked read_allow_patterns down to exclude these functions.
"""

from __future__ import annotations

import logging

from rfc_mcp.execution.invoker import ExecutionInvoker
from rfc_mcp.sap.exceptions import SAPError

logger = logging.getLogger("rfc_mcp.execution.source_reader")

# Global class-pool include naming convention: the class name padded to 30
# characters with '=', then a suffix identifying which part of the class
# (CP = class pool skeleton). WITH_INCLUDELIST='X' on that program is what
# actually discovers the real per-class include list (CU/CI/CO/CM<NNN>/...)
# rather than guessing which of them exist — confirmed against a real
# system multiple times: guessing suffixes without this failed for several
# classes until this two-phase approach was used instead.
_CLASS_POOL_PAD_WIDTH = 30
_CLASS_POOL_SUFFIX = "CP"


def _class_pool_program_name(class_name: str) -> str:
    return class_name.upper().ljust(_CLASS_POOL_PAD_WIDTH, "=") + _CLASS_POOL_SUFFIX


def _source_lines(result: dict, table_key: str) -> str:
    return "\n".join(line.get("LINE", "") for line in result.get(table_key, []))


def read_program_source(invoker: ExecutionInvoker, program_name: str) -> str:
    result = invoker.call("RPY_PROGRAM_READ", {"PROGRAM_NAME": program_name}, mode="read")
    return _source_lines(result, "SOURCE_EXTENDED")


def read_function_module_source(invoker: ExecutionInvoker, function_module_name: str) -> str:
    result = invoker.call(
        "RPY_FUNCTIONMODULE_READ", {"FUNCTIONNAME": function_module_name}, mode="read"
    )
    return _source_lines(result, "SOURCE")


def read_class_source(invoker: ExecutionInvoker, class_name: str) -> str:
    """Two-phase: discover the real include list via WITH_INCLUDELIST, then
    read every include and concatenate. This is what makes the RFC fallback
    path for classes reliable — no guessing which of CU/CI/CO/CM001... exist
    for a given class."""
    cp_name = _class_pool_program_name(class_name)
    cp_result = invoker.call(
        "RPY_PROGRAM_READ", {"PROGRAM_NAME": cp_name, "WITH_INCLUDELIST": "X"}, mode="read"
    )
    include_names = [
        row["INCLNAME"] for row in cp_result.get("INCLUDE_TAB", []) if row.get("INCLNAME")
    ]
    if not include_names:
        # No includes discovered - the class pool skeleton IS the source
        # (e.g. a very small/empty class with no implemented methods yet).
        return _source_lines(cp_result, "SOURCE_EXTENDED")

    parts = []
    for include_name in include_names:
        # One unreadable include (seen live: newer-release metadata-only
        # includes like a "CCAU" suffix that WITH_INCLUDELIST lists but
        # RPY_PROGRAM_READ can't actually return source for) must not fail
        # the whole class read — return everything that *did* read, noting
        # what didn't. PolicyDeniedError is NOT caught here: an operator
        # deliberately blocking RPY_PROGRAM_READ should still surface as a
        # real failure, not a silently-skipped include.
        try:
            include_result = invoker.call(
                "RPY_PROGRAM_READ", {"PROGRAM_NAME": include_name}, mode="read"
            )
        except SAPError as exc:
            logger.warning(
                "Could not read include %s of class %s: %s", include_name, class_name, exc
            )
            parts.append(f"* === INCLUDE {include_name} (unreadable: {exc}) ===")
            continue
        parts.append(f"* === INCLUDE {include_name} ===")
        parts.append(_source_lines(include_result, "SOURCE_EXTENDED"))
    return "\n\n".join(parts)
