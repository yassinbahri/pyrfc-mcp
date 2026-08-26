"""Expands a structure/table type name into its field list via
RFC_GET_STRUCTURE_DEFINITION. Exact field names of that function's FIELDS
table should be verified against the target SAP release once reachable;
this reads defensively via .get() rather than hard indexing.
"""

from __future__ import annotations

from rfc_mcp.discovery.models import FieldInfo
from rfc_mcp.sap.caller import RfcCaller


def resolve_structure_fields(
    caller: RfcCaller,
    tabname: str,
    *,
    max_depth: int = 8,
) -> list[FieldInfo]:
    """Return the flat field list for `tabname`. Guards against runaway
    recursion (a field row referencing its own or an ancestor's structure)
    with a depth cap and a seen-set of visited structure names.
    """
    if not tabname:
        return []
    return _resolve(caller, tabname, max_depth=max_depth, seen=set())


def _resolve(caller: RfcCaller, tabname: str, *, max_depth: int, seen: set[str]) -> list[FieldInfo]:
    upper_name = tabname.strip().upper()
    if not upper_name or upper_name in seen or max_depth <= 0:
        return []
    seen = seen | {upper_name}

    result = caller.call("RFC_GET_STRUCTURE_DEFINITION", TABNAME=tabname)
    raw_fields = result.get("FIELDS", [])

    fields: list[FieldInfo] = []
    for row in raw_fields:
        field_name = str(row.get("FIELDNAME", "")).strip()
        if not field_name:
            continue
        fields.append(
            FieldInfo(
                name=field_name,
                description=str(row.get("FIELDTEXT", "")).strip(),
                position=_as_int(row.get("POSITION")),
                abap_type=str(row.get("TYPE", "")).strip(),
                length=_as_int(row.get("LENG")),
                decimals=_as_int(row.get("DECIMALS")),
            )
        )

        # Some DDIC structures surface a nested structure/table reference on
        # a field row (e.g. an included substructure) rather than fully
        # flattening it. Expand it defensively if present.
        nested_tabname = str(row.get("TABNAME", "")).strip()
        if nested_tabname and nested_tabname.upper() != upper_name:
            fields.extend(_resolve(caller, nested_tabname, max_depth=max_depth - 1, seen=seen))

    return fields


def _as_int(value: object) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0
