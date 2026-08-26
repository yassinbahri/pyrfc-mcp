"""Canned RFC_FUNCTION_SEARCH / RFC_GET_FUNCTION_INTERFACE /
RFC_GET_STRUCTURE_DEFINITION payloads. Approximations of real SAP repository
function shapes for unit testing — not a guarantee of byte-for-byte accuracy
against any specific SAP release (see docs/architecture.md open risks).
"""

from __future__ import annotations

FUNCTION_SEARCH_RESULT: dict = {
    "FUNCTIONS": [
        {
            "FUNCNAME": "BAPI_CUSTOMER_GETLIST",
            "GROUPNAME": "VKD0",
            "STEXT": "Customer list",
            "REMOTE": "X",
        },
        {
            "FUNCNAME": "BAPI_CUSTOMER_GETDETAIL2",
            "GROUPNAME": "VKD0",
            "STEXT": "Customer detail",
            "REMOTE": "X",
        },
    ]
}

FUNCTION_INTERFACE_RESULT: dict = {
    "PARAMS": [
        {
            "PARAMETER": "CUSTOMERNO",
            "PARAMCLASS": "I",
            "PARAMTYPE": "KUNNR",
            "PARAMTEXT": "Customer number",
            "DEFAULT": "",
            "TABNAME": "",
            "OPTIONAL": "",
        },
        {
            "PARAMETER": "CUSTOMERDETAIL",
            "PARAMCLASS": "E",
            "PARAMTYPE": "BAPI_CUSTOMER_DETAIL",
            "PARAMTEXT": "Customer detail structure",
            "DEFAULT": "",
            "TABNAME": "BAPI_CUSTOMER_DETAIL",
            "OPTIONAL": "X",
        },
        {
            "PARAMETER": "RETURN",
            "PARAMCLASS": "T",
            "PARAMTYPE": "BAPIRET2",
            "PARAMTEXT": "Return messages",
            "DEFAULT": "",
            "TABNAME": "BAPIRET2",
            "OPTIONAL": "X",
        },
    ],
    "EXCEPTIONS": [
        {"EXCEPTION": "CUSTOMER_NOT_FOUND", "STEXT": "Customer does not exist"},
    ],
}

STRUCTURE_DEFINITIONS: dict[str, dict] = {
    "BAPI_CUSTOMER_DETAIL": {
        "FIELDS": [
            {
                "FIELDNAME": "CUSTOMER",
                "FIELDTEXT": "Customer number",
                "POSITION": "1",
                "TYPE": "CHAR",
                "LENG": "10",
                "DECIMALS": "0",
            },
            {
                "FIELDNAME": "NAME",
                "FIELDTEXT": "Name",
                "POSITION": "2",
                "TYPE": "CHAR",
                "LENG": "35",
                "DECIMALS": "0",
            },
        ]
    },
    "BAPIRET2": {
        "FIELDS": [
            {
                "FIELDNAME": "TYPE",
                "FIELDTEXT": "Message type",
                "POSITION": "1",
                "TYPE": "CHAR",
                "LENG": "1",
                "DECIMALS": "0",
            },
            {
                "FIELDNAME": "MESSAGE",
                "FIELDTEXT": "Message text",
                "POSITION": "2",
                "TYPE": "CHAR",
                "LENG": "220",
                "DECIMALS": "0",
            },
        ]
    },
}


def structure_definition_responder(params: dict) -> dict:
    tabname = params.get("TABNAME", "")
    return STRUCTURE_DEFINITIONS.get(tabname, {"FIELDS": []})


RPY_PROGRAM_READ_INTERFACE_RESULT: dict = {
    "PARAMS": [
        {
            "PARAMETER": "PROGRAM_NAME",
            "PARAMCLASS": "I",
            "PARAMTYPE": "",
            "PARAMTEXT": "",
            "DEFAULT": "",
            "TABNAME": "",
            "OPTIONAL": "",
        },
        {
            "PARAMETER": "WITH_INCLUDELIST",
            "PARAMCLASS": "I",
            "PARAMTYPE": "",
            "PARAMTEXT": "",
            "DEFAULT": "",
            "TABNAME": "",
            "OPTIONAL": "X",
        },
        {
            "PARAMETER": "SOURCE_EXTENDED",
            "PARAMCLASS": "T",
            "PARAMTYPE": "",
            "PARAMTEXT": "",
            "DEFAULT": "",
            "TABNAME": "",
            "OPTIONAL": "X",
        },
        {
            "PARAMETER": "INCLUDE_TAB",
            "PARAMCLASS": "T",
            "PARAMTYPE": "",
            "PARAMTEXT": "",
            "DEFAULT": "",
            "TABNAME": "",
            "OPTIONAL": "X",
        },
    ],
    "EXCEPTIONS": [],
}

RPY_FUNCTIONMODULE_READ_INTERFACE_RESULT: dict = {
    "PARAMS": [
        {
            "PARAMETER": "FUNCTIONNAME",
            "PARAMCLASS": "I",
            "PARAMTYPE": "",
            "PARAMTEXT": "",
            "DEFAULT": "",
            "TABNAME": "",
            "OPTIONAL": "",
        },
        {
            "PARAMETER": "SOURCE",
            "PARAMCLASS": "T",
            "PARAMTYPE": "",
            "PARAMTEXT": "",
            "DEFAULT": "",
            "TABNAME": "",
            "OPTIONAL": "X",
        },
    ],
    "EXCEPTIONS": [],
}


def function_interface_responder(params: dict) -> dict:
    """RFC_GET_FUNCTION_INTERFACE responder covering the fixed set of
    function names this test suite introspects — falls back to the generic
    BAPI_CUSTOMER_GETDETAIL2-shaped fixture for anything else."""
    funcname = params.get("FUNCNAME", "").upper()
    if funcname == "RPY_PROGRAM_READ":
        return RPY_PROGRAM_READ_INTERFACE_RESULT
    if funcname == "RPY_FUNCTIONMODULE_READ":
        return RPY_FUNCTIONMODULE_READ_INTERFACE_RESULT
    return FUNCTION_INTERFACE_RESULT
