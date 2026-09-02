from __future__ import annotations

import datetime
import decimal
import json

import pytest

from rfc_mcp.execution.result_transform import (
    ResultLimitExceededError,
    ResultLimitPolicy,
    to_json_safe,
)


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


def test_result_policy_accepts_exact_recursive_row_boundary():
    value = {"OUTER": [{"NESTED": [{"ID": 1}, {"ID": 2}]}]}

    assert ResultLimitPolicy(max_table_rows=3).apply(value) == value


def test_result_policy_rejects_cumulative_nested_rows_without_values():
    value = {
        "FIRST": [{"SECRET": "customer-a"}, {"SECRET": "customer-b"}],
        "SECOND": [{"SECRET": "customer-c"}],
    }

    with pytest.raises(ResultLimitExceededError) as exc_info:
        ResultLimitPolicy(max_table_rows=2).apply(value)

    message = str(exc_info.value)
    assert "actual=3" in message
    assert "limit=2" in message
    assert "customer" not in message


def test_result_policy_counts_multibyte_text_as_utf8_bytes():
    value = {"TEXT": "🦊"}
    compact_size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    assert ResultLimitPolicy(max_serialized_bytes=compact_size).apply(value) == value
    with pytest.raises(ResultLimitExceededError, match=f"actual={compact_size}, limit="):
        ResultLimitPolicy(max_serialized_bytes=compact_size - 1).apply(value)
