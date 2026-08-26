"""ConnectionPool logic (pooling, checkout/checkin, retry) tested against
FakeConnection via monkeypatching _import_pyrfc — no real pyrfc/SDK needed,
since these tests exercise our own pooling code, not pyrfc's exception
classes (that's test_sap_exceptions.py, guarded separately).
"""

from __future__ import annotations

import types
from contextlib import ExitStack

import pytest

from rfc_mcp.config import SAPConnectionSettings
from rfc_mcp.sap import connection as connection_module
from rfc_mcp.sap.connection import ConnectionPool, PooledCaller
from rfc_mcp.sap.exceptions import (
    SAPCommunicationError,
    SAPLogonError,
    SAPPoolTimeoutError,
    SAPUnavailableError,
)
from tests.fakes.fake_pyrfc import FakeConnection


def _settings(**overrides) -> SAPConnectionSettings:
    base = dict(
        ashost="h", sysnr="00", client="100", user="u", passwd="p", pool_size=2, max_retries=0
    )
    base.update(overrides)
    return SAPConnectionSettings(**base)


def _patch_pyrfc(monkeypatch, factory):
    fake_module = types.SimpleNamespace(Connection=factory)
    monkeypatch.setattr(connection_module, "_import_pyrfc", lambda: fake_module)


def test_acquire_creates_and_reuses_connection(monkeypatch):
    created: list[FakeConnection] = []

    def factory(*_a, **_k):
        conn = FakeConnection()
        created.append(conn)
        return conn

    _patch_pyrfc(monkeypatch, factory)
    pool = ConnectionPool(_settings())

    with pool.acquire() as conn1:
        assert conn1 is created[0]

    with pool.acquire() as conn2:
        assert conn2 is created[0]

    assert len(created) == 1


def test_acquire_discards_dead_connection(monkeypatch):
    created: list[FakeConnection] = []

    def factory(*_a, **_k):
        conn = FakeConnection()
        created.append(conn)
        return conn

    _patch_pyrfc(monkeypatch, factory)
    pool = ConnectionPool(_settings())

    with pool.acquire() as conn1:
        conn1.alive = False

    with pool.acquire() as conn2:
        assert conn2 is not conn1
        assert conn1.closed is True

    assert len(created) == 2


def test_pyrfc_unavailable_raises_clear_error(monkeypatch):
    def _raise():
        raise SAPUnavailableError("not installed")

    monkeypatch.setattr(connection_module, "_import_pyrfc", _raise)
    pool = ConnectionPool(_settings(max_retries=0))

    with pytest.raises(SAPUnavailableError), pool.acquire():
        pass


def test_pool_bounds_concurrent_connections(monkeypatch):
    created: list[FakeConnection] = []

    def factory(*_a, **_k):
        conn = FakeConnection()
        created.append(conn)
        return conn

    _patch_pyrfc(monkeypatch, factory)
    pool = ConnectionPool(_settings(pool_size=2))

    with pool.acquire() as c1, pool.acquire() as c2:
        assert c1 is not c2

    assert len(created) == 2


def test_pool_times_out_instead_of_blocking_forever(monkeypatch):
    _patch_pyrfc(monkeypatch, lambda *_a, **_k: FakeConnection())
    pool = ConnectionPool(_settings(pool_size=1, pool_acquire_timeout_seconds=0.01))

    with ExitStack() as stack:
        stack.enter_context(pool.acquire())
        with pytest.raises(SAPPoolTimeoutError):
            pool.checkout()


def test_connection_is_discarded_when_checked_out_call_raises(monkeypatch):
    created: list[FakeConnection] = []

    def factory(*_a, **_k):
        conn = FakeConnection()
        created.append(conn)
        return conn

    _patch_pyrfc(monkeypatch, factory)
    pool = ConnectionPool(_settings())

    with pytest.raises(RuntimeError), pool.acquire() as conn:
        raise RuntimeError("uncertain connection state")

    assert conn.closed is True
    with pool.acquire() as replacement:
        assert replacement is not conn


def test_connection_open_retries_only_communication_errors(monkeypatch):
    pool = ConnectionPool(_settings(max_retries=1, backoff_base_seconds=0.001))
    attempts = 0

    def create():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise SAPCommunicationError("temporary network failure")
        return FakeConnection()

    monkeypatch.setattr(pool, "_create_connection", create)
    with pool.acquire():
        pass
    assert attempts == 2


def test_connection_open_does_not_retry_logon_errors(monkeypatch):
    pool = ConnectionPool(_settings(max_retries=3))
    attempts = 0

    def create():
        nonlocal attempts
        attempts += 1
        raise SAPLogonError("bad credentials")

    monkeypatch.setattr(pool, "_create_connection", create)
    with pytest.raises(SAPLogonError), pool.acquire():
        pass
    assert attempts == 1


def test_pooled_caller_delegates_to_pool(monkeypatch):
    def factory(*_a, **_k):
        return FakeConnection(responses={"STFC_CONNECTION": {"ECHOTEXT": "hi"}})

    _patch_pyrfc(monkeypatch, factory)
    pool = ConnectionPool(_settings())
    caller = PooledCaller(pool)

    result = caller.call("STFC_CONNECTION", REQUTEXT="hi")
    assert result == {"ECHOTEXT": "hi"}
