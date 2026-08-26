from __future__ import annotations

from rfc_mcp.discovery.structure_resolver import resolve_structure_fields
from tests.fakes.fake_pyrfc import FakeConnection


def test_resolve_structure_fields_basic():
    caller = FakeConnection(
        responses={
            "RFC_GET_STRUCTURE_DEFINITION": lambda params: {
                "FIELDS": [
                    {
                        "FIELDNAME": "A",
                        "FIELDTEXT": "Field A",
                        "POSITION": "1",
                        "TYPE": "CHAR",
                        "LENG": "1",
                        "DECIMALS": "0",
                    },
                ]
            }
        }
    )
    fields = resolve_structure_fields(caller, "ZSTRUCT")
    assert [f.name for f in fields] == ["A"]


def test_resolve_structure_fields_empty_tabname_returns_empty():
    assert resolve_structure_fields(FakeConnection(), "") == []


def test_resolve_structure_fields_guards_against_cycles():
    def responder(_params):
        return {
            "FIELDS": [
                {
                    "FIELDNAME": "SELF",
                    "TABNAME": "ZSTRUCT",
                    "POSITION": "1",
                    "TYPE": "CHAR",
                    "LENG": "1",
                    "DECIMALS": "0",
                },
            ]
        }

    caller = FakeConnection(responses={"RFC_GET_STRUCTURE_DEFINITION": responder})
    fields = resolve_structure_fields(caller, "ZSTRUCT", max_depth=5)
    assert [f.name for f in fields] == ["SELF"]


def test_resolve_structure_fields_respects_max_depth():
    call_count = {"n": 0}

    def responder(_params):
        call_count["n"] += 1
        idx = call_count["n"]
        return {
            "FIELDS": [
                {
                    "FIELDNAME": f"F{idx}",
                    "TABNAME": f"ZNEST{idx + 1}",
                    "POSITION": "1",
                    "TYPE": "CHAR",
                    "LENG": "1",
                    "DECIMALS": "0",
                },
            ]
        }

    caller = FakeConnection(responses={"RFC_GET_STRUCTURE_DEFINITION": responder})
    fields = resolve_structure_fields(caller, "ZNEST1", max_depth=3)
    assert len(fields) == 3
