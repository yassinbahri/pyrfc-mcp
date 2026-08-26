"""Converts pyrfc.Connection.call() results (dicts with nested dicts for
structures, lists of dicts for tables, and possibly date/time/Decimal
scalars) into JSON-safe structures, recursively.
"""

from __future__ import annotations

import datetime
import decimal
from typing import Any


def to_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
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
