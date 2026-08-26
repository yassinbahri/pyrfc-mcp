from __future__ import annotations

from rfc_mcp.discovery.catalog import FunctionCatalog
from tests.fakes.fake_pyrfc import FakeConnection
from tests.fakes.sample_data import (
    FUNCTION_INTERFACE_RESULT,
    FUNCTION_SEARCH_RESULT,
    structure_definition_responder,
)


def _caller() -> FakeConnection:
    return FakeConnection(
        responses={
            "RFC_FUNCTION_SEARCH": FUNCTION_SEARCH_RESULT,
            "RFC_GET_FUNCTION_INTERFACE": FUNCTION_INTERFACE_RESULT,
            "RFC_GET_STRUCTURE_DEFINITION": structure_definition_responder,
        }
    )


def test_search_returns_normalized_summaries():
    catalog = FunctionCatalog(_caller())

    results = catalog.search("BAPI_CUSTOMER_*")

    assert [r.name for r in results] == ["BAPI_CUSTOMER_GETLIST", "BAPI_CUSTOMER_GETDETAIL2"]
    assert results[0].group == "VKD0"
    assert results[0].remote_enabled is True


def test_search_is_cached():
    caller = _caller()
    catalog = FunctionCatalog(caller, cache_ttl_seconds=60)

    catalog.search("BAPI_CUSTOMER_*")
    catalog.search("BAPI_CUSTOMER_*")

    search_calls = [c for c in caller.calls if c[0] == "RFC_FUNCTION_SEARCH"]
    assert len(search_calls) == 1


def test_get_interface_resolves_parameters_and_structures():
    catalog = FunctionCatalog(_caller())

    interface = catalog.get_interface("BAPI_CUSTOMER_GETDETAIL2")

    assert interface.name == "BAPI_CUSTOMER_GETDETAIL2"
    assert [p.name for p in interface.parameters] == ["CUSTOMERNO", "CUSTOMERDETAIL", "RETURN"]

    customerno = interface.parameter("CUSTOMERNO")
    assert customerno is not None
    assert customerno.param_class.value == "IMPORT"
    assert customerno.optional is False

    detail = interface.parameter("CUSTOMERDETAIL")
    assert detail is not None
    assert detail.param_class.value == "EXPORT"
    assert detail.optional is True
    assert [f.name for f in detail.fields] == ["CUSTOMER", "NAME"]

    ret = interface.parameter("RETURN")
    assert ret is not None
    assert ret.param_class.value == "TABLES"
    assert [f.name for f in ret.fields] == ["TYPE", "MESSAGE"]

    assert [e.name for e in interface.exceptions] == ["CUSTOMER_NOT_FOUND"]


def test_get_interface_is_cached():
    caller = _caller()
    catalog = FunctionCatalog(caller)

    catalog.get_interface("BAPI_CUSTOMER_GETDETAIL2")
    catalog.get_interface("BAPI_CUSTOMER_GETDETAIL2")

    interface_calls = [c for c in caller.calls if c[0] == "RFC_GET_FUNCTION_INTERFACE"]
    assert len(interface_calls) == 1
