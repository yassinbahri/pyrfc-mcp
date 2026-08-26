"""Validates caller-supplied JSON parameters against a resolved
FunctionInterface and builds the exact kwargs pyrfc.Connection.call() expects.
"""

from __future__ import annotations

from typing import Any

from rfc_mcp.discovery.models import FunctionInterface, ParamClass


class ParameterValidationError(Exception):
    pass


def build_call_kwargs(interface: FunctionInterface, parameters: dict[str, Any]) -> dict[str, Any]:
    provided_upper = {k.upper(): k for k in parameters}
    known_upper = {p.name.upper(): p for p in interface.parameters}

    unknown = [k for k in parameters if k.upper() not in known_upper]
    if unknown:
        raise ParameterValidationError(
            f"Unknown parameter(s) for {interface.name}: {', '.join(unknown)}"
        )

    missing_required = [
        p.name
        for p in interface.parameters
        if p.param_class == ParamClass.IMPORT
        and not p.optional
        and not p.default
        and p.name.upper() not in provided_upper
    ]
    if missing_required:
        raise ParameterValidationError(
            f"Missing required parameter(s) for {interface.name}: {', '.join(missing_required)}"
        )

    call_kwargs: dict[str, Any] = {}
    for p in interface.parameters:
        provided_key = provided_upper.get(p.name.upper())
        if provided_key is not None:
            call_kwargs[p.name] = parameters[provided_key]
    return call_kwargs
