"""Synthetic RFC backend for local evaluation without SAP or PyRFC.

The demo backend deliberately implements the same connection boundary used by
the real server. Discovery, interface resolution, policy enforcement,
parameter validation, result limits, and MCP serialization therefore remain
real; only the final RFC transport and its synthetic business records differ.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

DEMO_READ_ALLOW_PATTERNS = ["STFC_CONNECTION", "Z_DEMO_PRODUCT_LIST"]

_FUNCTIONS = (
    {
        "FUNCNAME": "STFC_CONNECTION",
        "GROUPNAME": "SYST",
        "STEXT": "Echo text through a synthetic RFC response",
        "REMOTE": "X",
    },
    {
        "FUNCNAME": "Z_DEMO_PRODUCT_LIST",
        "GROUPNAME": "ZMCP_DEMO",
        "STEXT": "Return synthetic products for local MCP evaluation",
        "REMOTE": "X",
    },
)

_INTERFACES: dict[str, dict[str, Any]] = {
    "STFC_CONNECTION": {
        "PARAMS": [
            {
                "PARAMETER": "REQUTEXT",
                "PARAMCLASS": "I",
                "PARAMTYPE": "CHAR255",
                "PARAMTEXT": "Text to echo",
                "DEFAULT": "",
                "TABNAME": "",
                "OPTIONAL": "",
            },
            {
                "PARAMETER": "ECHOTEXT",
                "PARAMCLASS": "E",
                "PARAMTYPE": "CHAR255",
                "PARAMTEXT": "Echoed text",
                "DEFAULT": "",
                "TABNAME": "",
                "OPTIONAL": "X",
            },
        ],
        "EXCEPTIONS": [],
    },
    "Z_DEMO_PRODUCT_LIST": {
        "PARAMS": [
            {
                "PARAMETER": "CATEGORY",
                "PARAMCLASS": "I",
                "PARAMTYPE": "CHAR20",
                "PARAMTEXT": "Optional category filter",
                "DEFAULT": "",
                "TABNAME": "",
                "OPTIONAL": "X",
            },
            {
                "PARAMETER": "PRODUCTS",
                "PARAMCLASS": "T",
                "PARAMTYPE": "ZDEMO_PRODUCT",
                "PARAMTEXT": "Synthetic product rows",
                "DEFAULT": "",
                "TABNAME": "ZDEMO_PRODUCT",
                "OPTIONAL": "X",
            },
        ],
        "EXCEPTIONS": [],
    },
}

_STRUCTURES: dict[str, dict[str, Any]] = {
    "ZDEMO_PRODUCT": {
        "FIELDS": [
            {
                "FIELDNAME": "PRODUCT_ID",
                "FIELDTEXT": "Synthetic product identifier",
                "POSITION": "1",
                "TYPE": "CHAR",
                "LENG": "10",
                "DECIMALS": "0",
            },
            {
                "FIELDNAME": "NAME",
                "FIELDTEXT": "Product name",
                "POSITION": "2",
                "TYPE": "CHAR",
                "LENG": "40",
                "DECIMALS": "0",
            },
            {
                "FIELDNAME": "CATEGORY",
                "FIELDTEXT": "Product category",
                "POSITION": "3",
                "TYPE": "CHAR",
                "LENG": "20",
                "DECIMALS": "0",
            },
        ]
    }
}

_PRODUCTS = (
    {"PRODUCT_ID": "P100", "NAME": "Demo Notebook", "CATEGORY": "OFFICE"},
    {"PRODUCT_ID": "P200", "NAME": "Demo Headset", "CATEGORY": "ELECTRONICS"},
    {"PRODUCT_ID": "P300", "NAME": "Demo Keyboard", "CATEGORY": "ELECTRONICS"},
)


class DemoConnection:
    """Small, deterministic stand-in for the PyRFC connection surface."""

    def __init__(self) -> None:
        self.alive = True

    def call(self, function_name: str, **params: Any) -> dict[str, Any]:
        name = function_name.strip().upper()
        if name == "RFC_FUNCTION_SEARCH":
            pattern = str(params.get("FUNCNAME", "*")).upper()
            group = str(params.get("GROUPNAME", "")).upper()
            functions = [
                dict(item)
                for item in _FUNCTIONS
                if fnmatch.fnmatchcase(str(item["FUNCNAME"]), pattern)
                and (not group or str(item["GROUPNAME"]).upper() == group)
            ]
            return {"FUNCTIONS": functions}
        if name == "RFC_GET_FUNCTION_INTERFACE":
            requested = str(params.get("FUNCNAME", "")).upper()
            return _copy_mapping(_INTERFACES.get(requested, {"PARAMS": [], "EXCEPTIONS": []}))
        if name == "RFC_GET_STRUCTURE_DEFINITION":
            requested = str(params.get("TABNAME", "")).upper()
            return _copy_mapping(_STRUCTURES.get(requested, {"FIELDS": []}))
        if name == "STFC_CONNECTION":
            text = str(params.get("REQUTEXT", ""))
            return {"ECHOTEXT": text, "RESPTEXT": "Synthetic demo response"}
        if name == "Z_DEMO_PRODUCT_LIST":
            category = str(params.get("CATEGORY", "")).strip().upper()
            products = [
                dict(item) for item in _PRODUCTS if not category or item["CATEGORY"] == category
            ]
            return {"PRODUCTS": products}
        raise ValueError(f"Demo RFC function is not available: {function_name}")

    def ping(self) -> bool:
        return self.alive

    def close(self) -> None:
        self.alive = False


class DemoConnectionPool:
    """Connection-manager implementation that never imports PyRFC."""

    @contextmanager
    def acquire(self) -> Iterator[DemoConnection]:
        connection = self.checkout()
        try:
            yield connection
        finally:
            self.release(connection)

    def checkout(self) -> DemoConnection:
        return DemoConnection()

    def release(self, conn: Any, *, reusable: bool = True) -> None:
        if isinstance(conn, DemoConnection):
            conn.close()

    def close_all(self) -> None:
        return None


def _copy_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """Copy the nested fixture shape so callers cannot mutate global data."""
    return {
        key: [dict(item) for item in item_value] if isinstance(item_value, list) else item_value
        for key, item_value in value.items()
    }
