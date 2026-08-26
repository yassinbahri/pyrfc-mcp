"""Stand-in for pyrfc.Connection matching the surface this codebase uses:
.call(), .alive, .ping(), .close(). Never imports pyrfc, so it works on any
Python version regardless of SDK availability.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FakeConnection:
    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        *,
        raises: dict[str, Exception] | None = None,
        fail_ping: bool = False,
        **_connection_kwargs: Any,
    ) -> None:
        """`responses` maps function name -> either a static dict result, or
        a callable(params) -> dict for responses that depend on the call
        arguments (e.g. RFC_GET_STRUCTURE_DEFINITION keyed by TABNAME).
        """
        self._responses = responses or {}
        self._raises = raises or {}
        self.alive = True
        self.closed = False
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._fail_ping = fail_ping

    def call(self, function_name: str, **params: Any) -> Any:
        self.calls.append((function_name, params))
        if function_name in self._raises:
            raise self._raises[function_name]
        response = self._responses.get(function_name, {})
        if callable(response):
            return response(params)
        return response

    def ping(self) -> bool:
        if self._fail_ping:
            raise RuntimeError("ping failed")
        return True

    def close(self) -> None:
        self.closed = True
        self.alive = False


def fake_connection_factory(
    **shared_kwargs: Any,
) -> Callable[..., FakeConnection]:
    """Returns a factory suitable for monkeypatching
    rfc_mcp.sap.connection._import_pyrfc()'s returned `pyrfc.Connection`:
    every call ignores real connection kwargs (ashost/client/user/...) and
    returns a fresh FakeConnection built from `shared_kwargs`.
    """

    def _factory(*_args: Any, **_kwargs: Any) -> FakeConnection:
        return FakeConnection(**shared_kwargs)

    return _factory
