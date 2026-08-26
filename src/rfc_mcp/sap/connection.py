"""SAP connection pooling. `import pyrfc` is confined to this module and is
always function-local, so the rest of the package stays importable and
unit-testable without pyrfc/the SDK installed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from rfc_mcp.config import SAPConnectionSettings
from rfc_mcp.sap.exceptions import (
    SAPCommunicationError,
    SAPPoolTimeoutError,
    SAPUnavailableError,
    translate_pyrfc_exception,
)

logger = logging.getLogger("rfc_mcp.sap.connection")


def _import_pyrfc() -> Any:
    try:
        import pyrfc
    except ImportError as exc:
        raise SAPUnavailableError(
            "pyrfc is not installed or the SAP NW RFC SDK could not be loaded "
            "(check SAPNWRFC_HOME and PATH). See docs/setup.md."
        ) from exc
    return pyrfc


class ConnectionPool:
    """Bounded pool of pyrfc.Connection objects.

    A single pyrfc.Connection is not safe for concurrent use from multiple
    threads — the semaphore + idle-list checkout/checkin discipline here is
    what enforces serialized access per connection.
    """

    def __init__(self, settings: SAPConnectionSettings) -> None:
        self._settings = settings
        self._idle: list[Any] = []
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(settings.pool_size)

    def _create_connection(self) -> Any:
        pyrfc = _import_pyrfc()
        kwargs = self._settings.to_pyrfc_kwargs()
        try:
            return pyrfc.Connection(config=self._settings.connection_config(), **kwargs)
        except Exception as exc:
            raise translate_pyrfc_exception(exc) from exc

    def _open_with_retry(self) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                return self._create_connection()
            except SAPCommunicationError as exc:
                last_exc = exc
                if attempt < self._settings.max_retries:
                    time.sleep(self._settings.backoff_base_seconds * (2**attempt))
            except Exception:
                # Authentication/configuration errors will not improve by
                # retrying and can lock or overload upstream systems.
                raise
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _is_alive(conn: Any) -> bool:
        try:
            if not conn.alive:
                return False
            conn.ping()
            return True
        except Exception:
            return False

    @staticmethod
    def _close_quietly(conn: Any) -> None:
        try:
            conn.close()
        except Exception:
            logger.debug("Error closing SAP connection", exc_info=True)

    @contextmanager
    def acquire(self) -> Iterator[Any]:
        conn = self.checkout()
        reusable = False
        try:
            yield conn
            reusable = True
        finally:
            self.release(conn, reusable=reusable)

    def checkout(self) -> Any:
        """Reserve one connection until ``release`` is called.

        The explicit checkout/release surface is used for SAP LUWs that must
        retain connection affinity across separate MCP tool requests.
        """
        acquired = self._semaphore.acquire(timeout=self._settings.pool_acquire_timeout_seconds)
        if not acquired:
            raise SAPPoolTimeoutError(
                "No SAP connection became available within "
                f"{self._settings.pool_acquire_timeout_seconds:g} seconds."
            )
        try:
            with self._lock:
                while self._idle:
                    candidate = self._idle.pop()
                    if self._is_alive(candidate):
                        return candidate
                    self._close_quietly(candidate)
            return self._open_with_retry()
        except BaseException:
            self._semaphore.release()
            raise

    def release(self, conn: Any, *, reusable: bool = True) -> None:
        """Return a reserved connection or discard it after an uncertain call."""
        try:
            if reusable:
                with self._lock:
                    self._idle.append(conn)
            else:
                self._close_quietly(conn)
        finally:
            self._semaphore.release()

    def close_all(self) -> None:
        with self._lock:
            idle, self._idle = self._idle, []
        for conn in idle:
            self._close_quietly(conn)


class PooledCaller:
    """Adapts a ConnectionPool to the single-call RfcCaller protocol used by
    the discovery and execution layers: acquire, call, release, per call.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def call(self, function_name: str, **params: Any) -> Any:
        with self._pool.acquire() as conn:
            try:
                return conn.call(function_name, **params)
            except Exception as exc:
                raise translate_pyrfc_exception(exc) from exc
