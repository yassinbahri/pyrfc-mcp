"""Function discovery: search + interface introspection, backed by SAP's
standard repository RFC modules (RFC_FUNCTION_SEARCH,
RFC_GET_FUNCTION_INTERFACE), normalized into discovery/models.py and cached.

Exact field names of these repository functions should be verified against
the target SAP release once reachable — this reads defensively via .get()
rather than hard indexing, per the plan's stated risk.
"""

from __future__ import annotations

from rfc_mcp.discovery.cache import TTLCache
from rfc_mcp.discovery.models import (
    ExceptionInfo,
    FunctionInterface,
    FunctionSummary,
    ParameterInfo,
    paramclass_from_code,
)
from rfc_mcp.discovery.structure_resolver import resolve_structure_fields
from rfc_mcp.sap.caller import RfcCaller


class FunctionCatalog:
    def __init__(
        self,
        caller: RfcCaller,
        *,
        cache_ttl_seconds: float = 300.0,
        structure_resolution_max_depth: int = 8,
    ) -> None:
        self._caller = caller
        self._max_depth = structure_resolution_max_depth
        self._search_cache: TTLCache[list[FunctionSummary]] = TTLCache(cache_ttl_seconds)
        self._interface_cache: TTLCache[FunctionInterface] = TTLCache(cache_ttl_seconds)

    def search(
        self, pattern: str, group: str | None = None, limit: int = 50
    ) -> list[FunctionSummary]:
        cache_key = f"{pattern.upper()}|{(group or '').upper()}|{limit}"

        def _do_search() -> list[FunctionSummary]:
            call_kwargs: dict[str, str] = {"FUNCNAME": pattern}
            if group:
                call_kwargs["GROUPNAME"] = group
            result = self._caller.call("RFC_FUNCTION_SEARCH", **call_kwargs)
            rows = result.get("FUNCTIONS", [])

            summaries: list[FunctionSummary] = []
            for row in rows[:limit]:
                name = str(row.get("FUNCNAME", "")).strip()
                if not name:
                    continue
                remote_flag = str(row.get("REMOTE", row.get("RFCREMOTE", "X"))).strip().upper()
                summaries.append(
                    FunctionSummary(
                        name=name,
                        group=str(row.get("GROUPNAME", "")).strip(),
                        short_text=str(row.get("STEXT", "")).strip(),
                        remote_enabled=remote_flag != "" and remote_flag != " ",
                    )
                )
            return summaries

        return self._search_cache.get_or_set(cache_key, _do_search)

    def get_interface(self, function_name: str) -> FunctionInterface:
        cache_key = function_name.upper()

        def _do_get_interface() -> FunctionInterface:
            result = self._caller.call("RFC_GET_FUNCTION_INTERFACE", FUNCNAME=function_name)

            parameters: list[ParameterInfo] = []
            for row in result.get("PARAMS", []):
                param_name = str(row.get("PARAMETER", "")).strip()
                if not param_name:
                    continue
                param_class_code = str(row.get("PARAMCLASS", "")).strip()
                try:
                    param_class = paramclass_from_code(param_class_code)
                except ValueError:
                    continue

                structure_name = str(row.get("TABNAME", "")).strip() or None
                fields = (
                    resolve_structure_fields(
                        self._caller, structure_name, max_depth=self._max_depth
                    )
                    if structure_name
                    else []
                )

                parameters.append(
                    ParameterInfo(
                        name=param_name,
                        param_class=param_class,
                        abap_type=str(row.get("PARAMTYPE", "")).strip(),
                        description=str(row.get("PARAMTEXT", "")).strip(),
                        default=str(row.get("DEFAULT", "")).strip(),
                        optional=str(row.get("OPTIONAL", "")).strip().upper() in ("X", "TRUE", "1"),
                        structure_name=structure_name,
                        fields=fields,
                    )
                )

            exceptions: list[ExceptionInfo] = []
            for row in result.get("EXCEPTIONS", []):
                exc_name = str(row.get("EXCEPTION", "")).strip()
                if not exc_name:
                    continue
                exceptions.append(
                    ExceptionInfo(
                        name=exc_name,
                        description=str(row.get("STEXT", row.get("DESCRIPTION", ""))).strip(),
                    )
                )

            return FunctionInterface(
                name=function_name, parameters=parameters, exceptions=exceptions
            )

        return self._interface_cache.get_or_set(cache_key, _do_get_interface)
