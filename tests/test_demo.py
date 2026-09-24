from __future__ import annotations

from rfc_mcp.config import PolicySettings
from rfc_mcp.demo import DEMO_READ_ALLOW_PATTERNS, DemoConnectionPool
from rfc_mcp.discovery.catalog import FunctionCatalog
from rfc_mcp.execution.invoker import ExecutionInvoker
from rfc_mcp.execution.policy import ExecutionPolicy
from rfc_mcp.sap.connection import PooledCaller
from rfc_mcp.sap.health import check_connectivity


def _runtime() -> tuple[FunctionCatalog, ExecutionInvoker]:
    pool = DemoConnectionPool()
    catalog = FunctionCatalog(PooledCaller(pool))
    policy = ExecutionPolicy(PolicySettings(read_allow_patterns=DEMO_READ_ALLOW_PATTERNS))
    return catalog, ExecutionInvoker(pool, catalog, policy)


def test_demo_backend_exercises_discovery_and_execution() -> None:
    catalog, invoker = _runtime()

    matches = catalog.search("Z_DEMO_*")
    assert [item.name for item in matches] == ["Z_DEMO_PRODUCT_LIST"]

    interface = catalog.get_interface("Z_DEMO_PRODUCT_LIST")
    products = interface.parameter("PRODUCTS")
    assert products is not None
    assert [field.name for field in products.fields] == ["PRODUCT_ID", "NAME", "CATEGORY"]

    result = invoker.call("Z_DEMO_PRODUCT_LIST", {"CATEGORY": "electronics"}, "read")
    assert [item["PRODUCT_ID"] for item in result["PRODUCTS"]] == ["P200", "P300"]


def test_demo_backend_echo_and_health() -> None:
    _, invoker = _runtime()

    result = invoker.call("STFC_CONNECTION", {"REQUTEXT": "hello"}, "read")

    assert result == {"ECHOTEXT": "hello", "RESPTEXT": "Synthetic demo response"}
    assert check_connectivity(DemoConnectionPool()).ok is True


def test_demo_search_honors_group_filter() -> None:
    catalog, _ = _runtime()

    assert catalog.search("*", group="SYST")[0].name == "STFC_CONNECTION"
    assert catalog.search("*", group="MISSING") == []
