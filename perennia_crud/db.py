import time
from contextlib import contextmanager

import pymysql
import pymysql.cursors
from pymysql.constants import CLIENT

from .config import DatabaseConfig
from .exceptions import CrudDatabaseError, DuplicateRecordError

# OperationalError codes that are typically transient (connection-level,
# not query-level) and safe to retry: can't connect, server gone away,
# lost connection, too many connections, lock wait timeout, deadlock.
_TRANSIENT_ERROR_CODES = {2003, 2006, 2013, 1040, 1205, 1213, 4031}


class Database:
    """Thin connection/transaction wrapper. Not a multi-engine abstraction.

    Retries only apply to establishing the connection, never to executing
    a statement — retrying a statement that may have already partially
    executed on the server risks applying it twice. Once a connection is
    open, a transient failure mid-transaction is translated and raised;
    it is the caller's responsibility to retry the whole operation if
    that's safe for it to do.
    """

    def __init__(self, config: DatabaseConfig, max_connect_retries: int = 0,
                 retry_backoff_seconds: float = 0.0):
        self._config = config
        self._max_connect_retries = max_connect_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def _connect(self):
        attempt = 0
        while True:
            try:
                return pymysql.connect(
                    host=self._config.host,
                    port=self._config.port,
                    user=self._config.user,
                    password=self._config.password,
                    database=self._config.database,
                    charset=self._config.charset,
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False,
                    connect_timeout=self._config.connect_timeout,
                    read_timeout=self._config.read_timeout,
                    write_timeout=self._config.write_timeout,
                    # Without this, pymysql reports rows *changed* for an
                    # UPDATE, not rows *matched*. A no-op update (new
                    # values equal old values) would then look identical
                    # to "no row matched", making rowcount unusable for
                    # detecting a record that disappeared out from under
                    # us. FOUND_ROWS makes rowcount mean "matched", which
                    # is what CrudEngine relies on.
                    client_flag=CLIENT.FOUND_ROWS,
                )
            except pymysql.err.OperationalError as e:
                code = e.args[0] if e.args else None
                if code in _TRANSIENT_ERROR_CODES and attempt < self._max_connect_retries:
                    time.sleep(self._retry_backoff_seconds * (2 ** attempt))
                    attempt += 1
                    continue
                raise CrudDatabaseError(f"Could not connect to database: {e}") from e
            except pymysql.MySQLError as e:
                raise CrudDatabaseError(f"Could not connect to database: {e}") from e

    @staticmethod
    def _reraise_translated(exc: Exception):
        if isinstance(exc, pymysql.err.IntegrityError):
            raise DuplicateRecordError(str(exc)) from exc
        if isinstance(exc, pymysql.MySQLError):
            raise CrudDatabaseError(str(exc)) from exc
        raise exc

    @contextmanager
    def transaction(self):
        """Yields a cursor. Commits on success, rolls back on any exception.

        Non-database exceptions raised inside the block (e.g. this
        library's own PerenniaCrudError subclasses, raised deliberately to
        abort a bulk operation) still trigger a rollback but are re-raised
        as-is, unchanged."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception as exc:
            conn.rollback()
            self._reraise_translated(exc)
        finally:
            conn.close()

    @contextmanager
    def cursor(self):
        """Read-only convenience cursor."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
        except Exception as exc:
            self._reraise_translated(exc)
        finally:
            conn.close()
