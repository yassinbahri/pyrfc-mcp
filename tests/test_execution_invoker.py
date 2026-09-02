from __future__ import annotations

from contextlib import contextmanager

import pytest

from rfc_mcp.config import PolicyMode, PolicySettings
from rfc_mcp.discovery.catalog import FunctionCatalog
from rfc_mcp.execution import invoker as invoker_module
from rfc_mcp.execution.invoker import ExecutionInvoker, TransactionNotFoundError
from rfc_mcp.execution.param_mapper import ParameterValidationError
from rfc_mcp.execution.policy import ExecutionPolicy, PolicyDeniedError
from rfc_mcp.execution.result_transform import (
    ResultLimitExceededError,
    ResultLimitPolicy,
)
from rfc_mcp.sap.exceptions import SAPError
from tests.fakes.fake_pyrfc import FakeConnection
from tests.fakes.sample_data import FUNCTION_INTERFACE_RESULT


class _FakePool:
    def __init__(self, *connections: FakeConnection) -> None:
        self._available = list(connections)
        self.releases: list[tuple[FakeConnection, bool]] = []

    def checkout(self) -> FakeConnection:
        if not self._available:
            raise RuntimeError("no fake connection available")
        return self._available.pop(0)

    def release(self, conn: FakeConnection, *, reusable: bool = True) -> None:
        self.releases.append((conn, reusable))
        if reusable:
            self._available.append(conn)
        else:
            conn.close()

    @contextmanager
    def acquire(self):
        conn = self.checkout()
        reusable = False
        try:
            yield conn
            reusable = True
        finally:
            self.release(conn, reusable=reusable)


def _catalog(caller: FakeConnection) -> FunctionCatalog:
    return FunctionCatalog(caller)


def _read_policy() -> ExecutionPolicy:
    return ExecutionPolicy(PolicySettings(mode=PolicyMode.READ_ONLY, read_allow_patterns=["*"]))


def _write_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        PolicySettings(
            mode=PolicyMode.READ_WRITE,
            read_allow_patterns=["*"],
            write_allow_patterns=["BAPI_CUSTOMER_*"],
            deny_patterns=[],
        )
    )


def _business_connection() -> FakeConnection:
    return FakeConnection(
        responses={
            "BAPI_CUSTOMER_GETDETAIL2": {"CUSTOMERDETAIL": {"CUSTOMER": "1"}},
            "BAPI_TRANSACTION_COMMIT": {"RETURN": []},
            "BAPI_TRANSACTION_ROLLBACK": {"RETURN": []},
        }
    )


def _interface_caller() -> FakeConnection:
    return FakeConnection(responses={"RFC_GET_FUNCTION_INTERFACE": FUNCTION_INTERFACE_RESULT})


def test_read_call_success_transforms_result():
    conn = _business_connection()
    invoker = ExecutionInvoker(_FakePool(conn), _catalog(_interface_caller()), _read_policy())

    result = invoker.call("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "read")

    assert result == {"CUSTOMERDETAIL": {"CUSTOMER": "1"}}


def test_read_call_blocks_oversized_result_without_logging_business_values(caplog):
    conn = FakeConnection(
        responses={"BAPI_CUSTOMER_GETDETAIL2": {"ROWS": [{"SECRET": "do-not-log"}]}}
    )
    invoker = ExecutionInvoker(
        _FakePool(conn),
        _catalog(_interface_caller()),
        _read_policy(),
        result_limits=ResultLimitPolicy(max_table_rows=1, max_serialized_bytes=10),
    )

    with pytest.raises(ResultLimitExceededError):
        invoker.call("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "read")

    assert "function=BAPI_CUSTOMER_GETDETAIL2" in caplog.text
    assert "max_serialized_bytes=10" in caplog.text
    assert "do-not-log" not in caplog.text


def test_call_blocked_by_policy_never_touches_connection():
    conn = _business_connection()
    policy = ExecutionPolicy(
        PolicySettings(
            mode=PolicyMode.READ_ONLY,
            read_allow_patterns=["*"],
            deny_patterns=["BAPI_*"],
        )
    )
    invoker = ExecutionInvoker(_FakePool(conn), _catalog(_interface_caller()), policy)

    with pytest.raises(PolicyDeniedError):
        invoker.call("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "read")

    assert not conn.calls


def test_call_rejects_invalid_parameters_before_touching_connection():
    conn = _business_connection()
    invoker = ExecutionInvoker(_FakePool(conn), _catalog(_interface_caller()), _read_policy())

    with pytest.raises(ParameterValidationError):
        invoker.call("BAPI_CUSTOMER_GETDETAIL2", {"BOGUS": "1"}, "read")

    assert not conn.calls


def test_call_translates_connection_exception_and_discards_connection():
    conn = FakeConnection(
        responses={"BAPI_TRANSACTION_ROLLBACK": {"RETURN": []}},
        raises={"BAPI_CUSTOMER_GETDETAIL2": RuntimeError("boom")},
    )
    pool = _FakePool(conn)
    invoker = ExecutionInvoker(pool, _catalog(_interface_caller()), _read_policy())

    with pytest.raises(SAPError):
        invoker.call("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "read")

    assert pool.releases == [(conn, False)]


def test_write_returns_transaction_id_and_commit_uses_same_connection():
    write_conn = _business_connection()
    other_conn = _business_connection()
    pool = _FakePool(write_conn, other_conn)
    invoker = ExecutionInvoker(pool, _catalog(_interface_caller()), _write_policy())

    _, tx_id = invoker.call_transactional("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "write")
    assert tx_id

    # A separate read consumes the other connection while the write LUW is pinned.
    invoker.call("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "read")
    invoker.commit(tx_id, wait=True)

    write_calls = [name for name, _ in write_conn.calls]
    other_calls = [name for name, _ in other_conn.calls]
    assert write_calls == ["BAPI_CUSTOMER_GETDETAIL2", "BAPI_TRANSACTION_COMMIT"]
    assert other_calls == ["BAPI_CUSTOMER_GETDETAIL2"]


def test_multiple_writes_can_reuse_transaction_id():
    conn = _business_connection()
    invoker = ExecutionInvoker(_FakePool(conn), _catalog(_interface_caller()), _write_policy())

    _, tx_id = invoker.call_transactional("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "write")
    _, reused_id = invoker.call_transactional(
        "BAPI_CUSTOMER_GETDETAIL2",
        {"CUSTOMERNO": "1"},
        "write",
        transaction_id=tx_id,
    )

    assert reused_id == tx_id
    invoker.rollback(tx_id)
    assert [name for name, _ in conn.calls][-1] == "BAPI_TRANSACTION_ROLLBACK"


def test_oversized_write_result_discards_transaction():
    conn = FakeConnection(responses={"BAPI_CUSTOMER_GETDETAIL2": {"ROWS": [{"ID": 1}, {"ID": 2}]}})
    pool = _FakePool(conn)
    invoker = ExecutionInvoker(
        pool,
        _catalog(_interface_caller()),
        _write_policy(),
        result_limits=ResultLimitPolicy(max_table_rows=1),
    )

    with pytest.raises(ResultLimitExceededError):
        invoker.call_transactional("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "write")

    assert pool.releases == [(conn, False)]


def test_completed_transaction_id_cannot_be_reused():
    conn = _business_connection()
    invoker = ExecutionInvoker(_FakePool(conn), _catalog(_interface_caller()), _write_policy())
    _, tx_id = invoker.call_transactional("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "write")
    assert tx_id is not None
    invoker.commit(tx_id)

    with pytest.raises(TransactionNotFoundError):
        invoker.commit(tx_id)


def test_transaction_control_requires_read_write_policy():
    invoker = ExecutionInvoker(
        _FakePool(_business_connection()),
        _catalog(_interface_caller()),
        _read_policy(),
    )
    with pytest.raises(PolicyDeniedError):
        invoker.commit("unknown")


def test_read_rejects_transaction_id():
    invoker = ExecutionInvoker(
        _FakePool(_business_connection()), _catalog(_interface_caller()), _read_policy()
    )
    with pytest.raises(ValueError, match="only valid for write"):
        invoker.call_transactional(
            "BAPI_CUSTOMER_GETDETAIL2",
            {"CUSTOMERNO": "1"},
            "read",
            transaction_id="not-valid-for-reads",
        )


def test_shutdown_rolls_back_open_transactions():
    conn = _business_connection()
    invoker = ExecutionInvoker(_FakePool(conn), _catalog(_interface_caller()), _write_policy())
    invoker.call_transactional("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "write")

    invoker.close()

    assert [name for name, _ in conn.calls][-1] == "BAPI_TRANSACTION_ROLLBACK"


def test_expired_transaction_is_rolled_back(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(invoker_module.time, "monotonic", lambda: now[0])
    conn = _business_connection()
    pool = _FakePool(conn)
    invoker = ExecutionInvoker(
        pool,
        _catalog(_interface_caller()),
        _write_policy(),
        transaction_ttl_seconds=10,
    )
    _, tx_id = invoker.call_transactional("BAPI_CUSTOMER_GETDETAIL2", {"CUSTOMERNO": "1"}, "write")
    assert tx_id is not None

    now[0] = 111.0
    with pytest.raises(TransactionNotFoundError):
        invoker.commit(tx_id)

    assert [name for name, _ in conn.calls][-1] == "BAPI_TRANSACTION_ROLLBACK"
