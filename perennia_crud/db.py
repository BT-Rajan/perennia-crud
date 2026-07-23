from contextlib import contextmanager

import pymysql
import pymysql.cursors

from .config import DatabaseConfig


class Database:
    """Thin connection/transaction wrapper. Not a multi-engine abstraction."""

    def __init__(self, config: DatabaseConfig):
        self._config = config

    def _connect(self):
        return pymysql.connect(
            host=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            database=self._config.database,
            charset=self._config.charset,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    @contextmanager
    def transaction(self):
        """Yields a cursor. Commits on success, rolls back on any exception."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def cursor(self):
        """Read-only convenience cursor."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
        finally:
            conn.close()
