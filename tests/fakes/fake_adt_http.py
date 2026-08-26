"""Stand-in transport for ADTClient's httpx.Client, via httpx.MockTransport.
Never makes a real network call, so these tests work with no ADT service
reachable — which, per docs/adt_rfc_integration_plan.md, is the actual state
of every system this project has been tested against so far.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx


def fake_adt_transport(
    responses: dict[str, httpx.Response] | None = None,
    *,
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> httpx.MockTransport:
    """`responses` maps request path -> a canned httpx.Response. `handler`,
    if given, takes precedence and lets a test build responses dynamically
    (e.g. asserting on query params)."""
    responses = responses or {}

    def _default_handler(request: httpx.Request) -> httpx.Response:
        response = responses.get(request.url.path)
        if response is None:
            return httpx.Response(404, text=f"no fake response registered for {request.url.path}")
        return response

    return httpx.MockTransport(handler or _default_handler)
