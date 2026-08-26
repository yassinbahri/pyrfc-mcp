from __future__ import annotations

import httpx
import pytest

from rfc_mcp.adt.client import ADTClient
from rfc_mcp.adt.exceptions import (
    ADTAuthenticationError,
    ADTConnectionError,
    ADTNotConfiguredError,
    ADTNotFoundError,
    ADTResponseError,
)
from rfc_mcp.config import ADTConnectionSettings
from tests.fakes.fake_adt_http import fake_adt_transport


def _settings(**overrides) -> ADTConnectionSettings:
    base = {
        "enabled": True,
        "host": "h",
        "client": "100",
        "user": "u",
        "passwd": "p",
        "max_retries": 0,
    }
    base.update(overrides)
    return ADTConnectionSettings(**base)


def test_client_rejects_construction_when_not_enabled():
    with pytest.raises(ADTNotConfiguredError):
        ADTClient(ADTConnectionSettings(enabled=False))


def test_get_program_source_returns_text():
    transport = fake_adt_transport(
        {"/sap/bc/adt/programs/programs/ZFOO/source/main": httpx.Response(200, text="REPORT zfoo.")}
    )
    client = ADTClient(_settings(), transport=transport)
    assert client.get_program_source("ZFOO") == "REPORT zfoo."


def test_get_class_source_returns_whole_class_in_one_call():
    transport = fake_adt_transport(
        {
            "/sap/bc/adt/oo/classes/ZCL_FOO/source/main": httpx.Response(
                200, text="CLASS zcl_foo DEFINITION.\nENDCLASS."
            )
        }
    )
    client = ADTClient(_settings(), transport=transport)
    source = client.get_class_source("ZCL_FOO")
    assert "ENDCLASS" in source


def test_get_function_module_source_uses_group_and_module():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sap/bc/adt/functions/groups/ZFG/fmodules/Z_FOO/source/main"
        return httpx.Response(200, text="FUNCTION z_foo.")

    transport = fake_adt_transport(handler=handler)
    client = ADTClient(_settings(), transport=transport)
    assert client.get_function_module_source("ZFG", "Z_FOO") == "FUNCTION z_foo."


def test_accept_header_is_text_plain():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["accept"] = request.headers.get("accept")
        return httpx.Response(200, text="ok")

    transport = fake_adt_transport(handler=handler)
    client = ADTClient(_settings(), transport=transport)
    client.get_program_source("ZFOO")
    assert seen_headers["accept"] == "text/plain"


def test_sap_client_sent_as_query_param():
    seen_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params["sap-client"] = request.url.params.get("sap-client")
        return httpx.Response(200, text="ok")

    transport = fake_adt_transport(handler=handler)
    client = ADTClient(_settings(client="100"), transport=transport)
    client.get_program_source("ZFOO")
    assert seen_params["sap-client"] == "100"


def test_404_translates_to_adt_not_found_error():
    transport = fake_adt_transport(
        {"/sap/bc/adt/programs/programs/ZMISSING/source/main": httpx.Response(404)}
    )
    client = ADTClient(_settings(), transport=transport)
    with pytest.raises(ADTNotFoundError):
        client.get_program_source("ZMISSING")


def test_401_translates_to_adt_authentication_error():
    transport = fake_adt_transport(
        {"/sap/bc/adt/programs/programs/ZFOO/source/main": httpx.Response(401)}
    )
    client = ADTClient(_settings(), transport=transport)
    with pytest.raises(ADTAuthenticationError):
        client.get_program_source("ZFOO")


def test_4xx_is_not_retried():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(404)

    transport = fake_adt_transport(handler=handler)
    client = ADTClient(_settings(max_retries=3), transport=transport)
    with pytest.raises(ADTNotFoundError):
        client.get_program_source("ZFOO")
    assert call_count["n"] == 1


def test_5xx_is_retried_up_to_max_retries_then_raises():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(500, text="internal error")

    transport = fake_adt_transport(handler=handler)
    client = ADTClient(_settings(max_retries=2, backoff_base_seconds=0.01), transport=transport)
    with pytest.raises(ADTResponseError):
        client.get_program_source("ZFOO")
    assert call_count["n"] == 3  # initial attempt + 2 retries


def test_5xx_succeeds_after_transient_failure():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 2:
            return httpx.Response(500)
        return httpx.Response(200, text="REPORT zfoo.")

    transport = fake_adt_transport(handler=handler)
    client = ADTClient(_settings(max_retries=3, backoff_base_seconds=0.01), transport=transport)
    assert client.get_program_source("ZFOO") == "REPORT zfoo."
    assert call_count["n"] == 2


def test_transport_error_translates_to_adt_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = fake_adt_transport(handler=handler)
    client = ADTClient(_settings(max_retries=0), transport=transport)
    with pytest.raises(ADTConnectionError):
        client.get_program_source("ZFOO")


def test_context_manager_closes_client():
    transport = fake_adt_transport(
        {"/sap/bc/adt/programs/programs/ZFOO/source/main": httpx.Response(200, text="x")}
    )
    with ADTClient(_settings(), transport=transport) as client:
        client.get_program_source("ZFOO")
    with pytest.raises(RuntimeError):
        client.get_program_source("ZFOO")
