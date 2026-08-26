"""Normalized discovery models. Pure pydantic — populated from RFC repository
function results by discovery/catalog.py and discovery/structure_resolver.py,
never constructed directly from raw SAP dicts elsewhere.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ParamClass(StrEnum):
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    TABLES = "TABLES"
    CHANGING = "CHANGING"


_PARAMCLASS_CODE_MAP = {
    "I": ParamClass.IMPORT,
    "E": ParamClass.EXPORT,
    "T": ParamClass.TABLES,
    "C": ParamClass.CHANGING,
}


def paramclass_from_code(code: str) -> ParamClass:
    try:
        return _PARAMCLASS_CODE_MAP[code.strip().upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown RFC PARAMCLASS code: {code!r}") from exc


class FieldInfo(BaseModel):
    """A single field of a structure/table type, from
    RFC_GET_STRUCTURE_DEFINITION."""

    name: str
    description: str = ""
    position: int = 0
    abap_type: str = ""
    length: int = 0
    decimals: int = 0


class ParameterInfo(BaseModel):
    """A single IMPORT/EXPORT/TABLES/CHANGING parameter of a function module,
    from RFC_GET_FUNCTION_INTERFACE, with structure fields resolved (if
    applicable) by structure_resolver.
    """

    name: str
    param_class: ParamClass
    abap_type: str = ""
    description: str = ""
    default: str = ""
    optional: bool = False
    structure_name: str | None = None
    fields: list[FieldInfo] = Field(default_factory=list)


class ExceptionInfo(BaseModel):
    name: str
    description: str = ""


class FunctionSummary(BaseModel):
    """One search result row from RFC_FUNCTION_SEARCH."""

    name: str
    group: str = ""
    short_text: str = ""
    remote_enabled: bool = True


class FunctionInterface(BaseModel):
    """Full introspected interface of a function module."""

    name: str
    parameters: list[ParameterInfo] = Field(default_factory=list)
    exceptions: list[ExceptionInfo] = Field(default_factory=list)

    def parameter(self, name: str) -> ParameterInfo | None:
        for p in self.parameters:
            if p.name.upper() == name.upper():
                return p
        return None
