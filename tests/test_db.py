from unittest.mock import MagicMock, patch

import pymysql
import pytest

from perennia_crud.config import DatabaseConfig
from perennia_crud.db import Database
from perennia_crud.exceptions import CrudDatabaseError, DuplicateRecordError


def _config():
    return DatabaseConfig(host="db", user="app", password="x", database="test")


@patch("perennia_crud.db.pymysql.connect")
def test_transaction_commits_on_success(mock_connect):
    conn = MagicMock()
    mock_connect.return_value = conn
    db = Database(_config())

    with db.transaction() as cur:
        assert cur is conn.cursor.return_value

    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
    conn.close.assert_called_once()


@patch("perennia_crud.db.pymysql.connect")
def test_transaction_rolls_back_and_translates_integrity_error(mock_connect):
    conn = MagicMock()
    mock_connect.return_value = conn
    db = Database(_config())

    with pytest.raises(DuplicateRecordError):
        with db.transaction() as cur:
            raise pymysql.err.IntegrityError(1062, "Duplicate entry")

    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


@patch("perennia_crud.db.pymysql.connect")
def test_transaction_translates_generic_mysql_error(mock_connect):
    conn = MagicMock()
    mock_connect.return_value = conn
    db = Database(_config())

    with pytest.raises(CrudDatabaseError):
        with db.transaction() as cur:
            raise pymysql.err.OperationalError(2013, "Lost connection")

    conn.rollback.assert_called_once()


@patch("perennia_crud.db.pymysql.connect")
def test_transaction_passes_through_non_database_errors(mock_connect):
    """A deliberate business-logic exception raised inside the block (e.g.
    RecordNotFoundError from a bulk operation) must still roll back but
    must NOT be translated into a database error."""
    conn = MagicMock()
    mock_connect.return_value = conn
    db = Database(_config())

    class CustomError(Exception):
        pass

    with pytest.raises(CustomError):
        with db.transaction() as cur:
            raise CustomError("business rule violated")

    conn.rollback.assert_called_once()


@patch("perennia_crud.db.time.sleep", return_value=None)
@patch("perennia_crud.db.pymysql.connect")
def test_connect_retries_transient_failure_then_succeeds(mock_connect, mock_sleep):
    good_conn = MagicMock()
    mock_connect.side_effect = [
        pymysql.err.OperationalError(2003, "Can't connect to MySQL server"),
        good_conn,
    ]
    db = Database(_config(), max_connect_retries=2, retry_backoff_seconds=0.01)

    with db.cursor() as cur:
        pass

    assert mock_connect.call_count == 2
    mock_sleep.assert_called_once()


@patch("perennia_crud.db.time.sleep", return_value=None)
@patch("perennia_crud.db.pymysql.connect")
def test_connect_gives_up_after_max_retries(mock_connect, mock_sleep):
    mock_connect.side_effect = pymysql.err.OperationalError(2003, "Can't connect")
    db = Database(_config(), max_connect_retries=2, retry_backoff_seconds=0.01)

    with pytest.raises(CrudDatabaseError):
        with db.cursor() as cur:
            pass

    assert mock_connect.call_count == 3  # initial attempt + 2 retries


@patch("perennia_crud.db.pymysql.connect")
def test_connect_does_not_retry_non_transient_error(mock_connect):
    mock_connect.side_effect = pymysql.err.OperationalError(1045, "Access denied")
    db = Database(_config(), max_connect_retries=3, retry_backoff_seconds=0.01)

    with pytest.raises(CrudDatabaseError):
        with db.cursor() as cur:
            pass

    assert mock_connect.call_count == 1
