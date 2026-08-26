from __future__ import annotations

from rfc_mcp.execution import transaction
from tests.fakes.fake_pyrfc import FakeConnection


def test_commit_calls_bapi_transaction_commit_with_wait_flag():
    caller = FakeConnection(responses={"BAPI_TRANSACTION_COMMIT": {"RETURN": []}})
    transaction.commit(caller, wait=True)
    name, params = caller.calls[-1]
    assert name == "BAPI_TRANSACTION_COMMIT"
    assert params["WAIT"] == "X"


def test_commit_without_wait():
    caller = FakeConnection(responses={"BAPI_TRANSACTION_COMMIT": {"RETURN": []}})
    transaction.commit(caller, wait=False)
    _, params = caller.calls[-1]
    assert params["WAIT"] == ""


def test_rollback_calls_bapi_transaction_rollback():
    caller = FakeConnection(responses={"BAPI_TRANSACTION_ROLLBACK": {"RETURN": []}})
    transaction.rollback(caller)
    name, _ = caller.calls[-1]
    assert name == "BAPI_TRANSACTION_ROLLBACK"
