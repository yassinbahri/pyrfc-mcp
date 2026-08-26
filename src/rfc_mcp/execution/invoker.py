"""Policy, parameter mapping, connection affinity, and result shaping.

Read calls borrow a pooled connection for one operation. Write calls reserve a
connection for an explicit transaction ID so every subsequent write and the
eventual commit/rollback remain in the same SAP LUW.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from rfc_mcp.discovery.catalog import FunctionCatalog
from rfc_mcp.execution import transaction
from rfc_mcp.execution.param_mapper import build_call_kwargs
from rfc_mcp.execution.policy import ExecutionPolicy
from rfc_mcp.execution.result_transform import to_json_safe
from rfc_mcp.sap.connection import ConnectionPool
from rfc_mcp.sap.exceptions import translate_pyrfc_exception

logger = logging.getLogger("rfc_mcp.execution.invoker")


class TransactionNotFoundError(ValueError):
    """A transaction ID is unknown, expired, or already completed."""


@dataclass
class _ActiveTransaction:
    connection: Any
    last_used: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class ExecutionInvoker:
    def __init__(
        self,
        pool: ConnectionPool,
        catalog: FunctionCatalog,
        policy: ExecutionPolicy,
        *,
        transaction_ttl_seconds: float = 300.0,
    ) -> None:
        self._pool = pool
        self._catalog = catalog
        self._policy = policy
        self._transaction_ttl_seconds = transaction_ttl_seconds
        self._transactions: dict[str, _ActiveTransaction] = {}
        self._transactions_lock = threading.Lock()

    def call(self, function_name: str, parameters: dict[str, Any], mode: str) -> dict[str, Any]:
        """Execute a read call; writes must use ``call_transactional``."""
        if mode != "read":
            raise ValueError(
                "Write calls require call_transactional() so they can return "
                "the SAP transaction ID."
            )
        self._policy.authorize(function_name, mode, parameters)
        interface = self._catalog.get_interface(function_name)
        call_kwargs = build_call_kwargs(interface, parameters)
        with self._pool.acquire() as conn:
            result = self._call_on_connection(conn, function_name, call_kwargs, mode)
        return to_json_safe(result)

    def call_transactional(
        self,
        function_name: str,
        parameters: dict[str, Any],
        mode: str,
        transaction_id: str | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        """Execute a tool call and return its result plus transaction ID.

        A first write reserves a pooled connection and creates an opaque ID.
        Passing that ID to later writes keeps them in the same SAP LUW. Reads
        never accept a transaction ID because they do not need session state.
        """
        self._expire_transactions()
        if mode == "read":
            if transaction_id is not None:
                raise ValueError("transaction_id is only valid for write calls")
            return self.call(function_name, parameters, mode), None
        if mode != "write":
            raise ValueError(f"Unknown mode: {mode!r}")

        self._policy.authorize(function_name, mode, parameters)
        interface = self._catalog.get_interface(function_name)
        call_kwargs = build_call_kwargs(interface, parameters)

        tx_id, active = self._get_or_create_transaction(transaction_id)
        with active.lock:
            if not self._is_current_transaction(tx_id, active):
                raise TransactionNotFoundError(self._transaction_error(tx_id))
            try:
                result = self._call_on_connection(
                    active.connection,
                    function_name,
                    call_kwargs,
                    mode,
                    transaction_id=tx_id,
                )
            except Exception:
                self._discard_transaction(tx_id, active)
                raise
            active.last_used = time.monotonic()
        return to_json_safe(result), tx_id

    def commit(self, transaction_id: str, wait: bool = False) -> dict[str, Any]:
        self._policy.authorize_transaction_control()
        return self._finish_transaction(transaction_id, "commit", wait=wait)

    def rollback(self, transaction_id: str) -> dict[str, Any]:
        self._policy.authorize_transaction_control()
        return self._finish_transaction(transaction_id, "rollback")

    def close(self) -> None:
        """Best-effort rollback of abandoned LUWs during server shutdown."""
        with self._transactions_lock:
            pending = list(self._transactions.items())
            self._transactions.clear()
        for tx_id, active in pending:
            with active.lock:
                reusable = False
                try:
                    transaction.rollback(active.connection)
                    reusable = True
                    logger.info("ROLLBACK SUCCEEDED transaction_id=%s reason=shutdown", tx_id)
                except Exception:
                    logger.warning(
                        "ROLLBACK FAILED transaction_id=%s reason=shutdown",
                        tx_id,
                        exc_info=True,
                    )
                finally:
                    self._pool.release(active.connection, reusable=reusable)

    def _call_on_connection(
        self,
        conn: Any,
        function_name: str,
        call_kwargs: dict[str, Any],
        mode: str,
        transaction_id: str | None = None,
    ) -> Any:
        try:
            result = conn.call(function_name, **call_kwargs)
        except Exception as exc:
            translated = translate_pyrfc_exception(exc)
            logger.warning(
                "CALL FAILED function=%s mode=%s transaction_id=%s error=%s: %s",
                function_name,
                mode,
                transaction_id,
                type(translated).__name__,
                translated,
            )
            raise translated from exc
        logger.info(
            "CALL SUCCEEDED function=%s mode=%s transaction_id=%s",
            function_name,
            mode,
            transaction_id,
        )
        return result

    def _get_or_create_transaction(
        self, transaction_id: str | None
    ) -> tuple[str, _ActiveTransaction]:
        if transaction_id is not None:
            with self._transactions_lock:
                active = self._transactions.get(transaction_id)
            if active is None:
                raise TransactionNotFoundError(self._transaction_error(transaction_id))
            return transaction_id, active

        conn = self._pool.checkout()
        tx_id = secrets.token_urlsafe(24)
        active = _ActiveTransaction(connection=conn, last_used=time.monotonic())
        with self._transactions_lock:
            self._transactions[tx_id] = active
        logger.info("TRANSACTION STARTED transaction_id=%s", tx_id)
        return tx_id, active

    def _finish_transaction(
        self, transaction_id: str, action: str, *, wait: bool = False
    ) -> dict[str, Any]:
        self._expire_transactions()
        with self._transactions_lock:
            active = self._transactions.get(transaction_id)
        if active is None:
            raise TransactionNotFoundError(self._transaction_error(transaction_id))

        with active.lock:
            if not self._remove_if_current(transaction_id, active):
                raise TransactionNotFoundError(self._transaction_error(transaction_id))
            reusable = False
            try:
                if action == "commit":
                    result = transaction.commit(active.connection, wait=wait)
                else:
                    result = transaction.rollback(active.connection)
                reusable = True
            except Exception as exc:
                translated = translate_pyrfc_exception(exc)
                logger.warning(
                    "%s FAILED transaction_id=%s error=%s: %s",
                    action.upper(),
                    transaction_id,
                    type(translated).__name__,
                    translated,
                )
                raise translated from exc
            finally:
                self._pool.release(active.connection, reusable=reusable)
        logger.info("%s SUCCEEDED transaction_id=%s", action.upper(), transaction_id)
        return to_json_safe(result)

    def _expire_transactions(self) -> None:
        cutoff = time.monotonic() - self._transaction_ttl_seconds
        with self._transactions_lock:
            candidates = list(self._transactions.items())
        for tx_id, active in candidates:
            if active.last_used >= cutoff or not active.lock.acquire(blocking=False):
                continue
            try:
                with self._transactions_lock:
                    if self._transactions.get(tx_id) is not active or active.last_used >= cutoff:
                        continue
                    del self._transactions[tx_id]
                reusable = False
                try:
                    transaction.rollback(active.connection)
                    reusable = True
                except Exception:
                    logger.warning(
                        "ROLLBACK FAILED transaction_id=%s reason=expired",
                        tx_id,
                        exc_info=True,
                    )
                finally:
                    self._pool.release(active.connection, reusable=reusable)
                logger.warning("TRANSACTION EXPIRED transaction_id=%s", tx_id)
            finally:
                active.lock.release()

    def _discard_transaction(self, transaction_id: str, active: _ActiveTransaction) -> None:
        if self._remove_if_current(transaction_id, active):
            self._pool.release(active.connection, reusable=False)
            logger.warning("TRANSACTION DISCARDED transaction_id=%s", transaction_id)

    def _is_current_transaction(self, transaction_id: str, active: _ActiveTransaction) -> bool:
        with self._transactions_lock:
            return self._transactions.get(transaction_id) is active

    def _remove_if_current(self, transaction_id: str, active: _ActiveTransaction) -> bool:
        with self._transactions_lock:
            if self._transactions.get(transaction_id) is not active:
                return False
            del self._transactions[transaction_id]
            return True

    @staticmethod
    def _transaction_error(transaction_id: str) -> str:
        return (
            f"Unknown or expired transaction_id {transaction_id!r}; it may "
            "already have been committed, rolled back, or discarded after an error."
        )
