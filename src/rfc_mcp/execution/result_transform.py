"""Converts pyrfc.Connection.call() results (dicts with nested dicts for
structures, lists of dicts for tables, and possibly date/time/Decimal
scalars) into JSON-safe structures, recursively.
"""

from __future__ import annotations

import datetime
import decimal
import json
from dataclasses import dataclass
from typing import Any


class ResultLimitExceededError(ValueError):
    """An RFC result exceeded an operator-configured response boundary."""


@dataclass(frozen=True)
class ResultLimitPolicy:
    """Fail-closed limits applied before an RFC result reaches MCP."""

    max_table_rows: int = 10_000
    max_serialized_bytes: int = 1_048_576

    def apply(self, value: Any) -> Any:
        rows = [0]
        result = _to_json_safe(value, rows=rows, max_table_rows=self.max_table_rows)
        serialized_bytes = len(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if serialized_bytes > self.max_serialized_bytes:
            raise ResultLimitExceededError(
                "RFC result exceeds max_serialized_bytes "
                f"(actual={serialized_bytes}, limit={self.max_serialized_bytes})"
            )
        return result


def to_json_safe(value: Any) -> Any:
    """Convert an RFC result without applying response limits."""
    return _to_json_safe(value)


def _to_json_safe(
    value: Any,
    *,
    rows: list[int] | None = None,
    max_table_rows: int | None = None,
) -> Any:
    if isinstance(value, dict):
        return {
            k: _to_json_safe(v, rows=rows, max_table_rows=max_table_rows) for k, v in value.items()
        }
    if isinstance(value, list):
        if rows is not None and max_table_rows is not None:
            rows[0] += len(value)
            if rows[0] > max_table_rows:
                raise ResultLimitExceededError(
                    f"RFC result exceeds max_table_rows (actual={rows[0]}, limit={max_table_rows})"
                )
        return [_to_json_safe(v, rows=rows, max_table_rows=max_table_rows) for v in value]
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
