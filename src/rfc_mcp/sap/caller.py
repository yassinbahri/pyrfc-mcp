"""Shared calling protocol used by discovery and execution so neither layer
needs to import pyrfc or the ConnectionPool directly — they depend on this
narrow interface instead, which both pyrfc.Connection and
tests/fakes/fake_pyrfc.FakeConnection satisfy structurally.
"""

from __future__ import annotations

from typing import Any, Protocol


class RfcCaller(Protocol):
    def call(self, function_name: str, **params: Any) -> dict[str, Any]: ...
