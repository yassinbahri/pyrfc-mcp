from __future__ import annotations

import pytest

from rfc_mcp.discovery.models import FunctionInterface, ParamClass, ParameterInfo
from rfc_mcp.execution.param_mapper import ParameterValidationError, build_call_kwargs


def _interface() -> FunctionInterface:
    return FunctionInterface(
        name="BAPI_CUSTOMER_GETDETAIL2",
        parameters=[
            ParameterInfo(name="CUSTOMERNO", param_class=ParamClass.IMPORT, optional=False),
            ParameterInfo(name="LANGU", param_class=ParamClass.IMPORT, optional=True, default="EN"),
            ParameterInfo(name="CUSTOMERDETAIL", param_class=ParamClass.EXPORT, optional=True),
        ],
    )


def test_build_call_kwargs_maps_provided_params():
    kwargs = build_call_kwargs(_interface(), {"CUSTOMERNO": "0000001000"})
    assert kwargs == {"CUSTOMERNO": "0000001000"}


def test_build_call_kwargs_case_insensitive_and_canonicalized():
    kwargs = build_call_kwargs(_interface(), {"customerno": "0000001000"})
    assert kwargs == {"CUSTOMERNO": "0000001000"}


def test_build_call_kwargs_rejects_unknown_parameter():
    with pytest.raises(ParameterValidationError):
        build_call_kwargs(_interface(), {"CUSTOMERNO": "1", "BOGUS": "x"})


def test_build_call_kwargs_rejects_missing_required():
    with pytest.raises(ParameterValidationError):
        build_call_kwargs(_interface(), {})


def test_build_call_kwargs_allows_missing_optional_with_default():
    kwargs = build_call_kwargs(_interface(), {"CUSTOMERNO": "1"})
    assert "LANGU" not in kwargs
