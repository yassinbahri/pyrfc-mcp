from __future__ import annotations

import datetime
import decimal

from rfc_mcp.execution.result_transform import to_json_safe


def test_scalars_pass_through():
    assert to_json_safe("x") == "x"
    assert to_json_safe(1) == 1
    assert to_json_safe(True) is True
    assert to_json_safe(None) is None


def test_date_time_converted_to_iso():
    assert to_json_safe(datetime.date(2026, 1, 1)) == "2026-01-01"
    assert to_json_safe(datetime.time(12, 30)) == "12:30:00"
    assert to_json_safe(datetime.datetime(2026, 1, 1, 12, 30)) == "2026-01-01T12:30:00"


def test_decimal_converted_to_string():
    assert to_json_safe(decimal.Decimal("10.50")) == "10.50"


def test_nested_structures_preserved():
    value = {
        "RETURN": [{"TYPE": "S", "MESSAGE": "ok", "AMOUNT": decimal.Decimal("1.5")}],
        "DETAIL": {"NAME": "ACME", "SINCE": datetime.date(2020, 1, 1)},
    }
    result = to_json_safe(value)
    assert result["RETURN"][0]["AMOUNT"] == "1.5"
    assert result["DETAIL"]["SINCE"] == "2020-01-01"


def test_bytes_decoded():
    assert to_json_safe(b"hello") == "hello"
