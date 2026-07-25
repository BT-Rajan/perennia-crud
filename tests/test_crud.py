from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from perennia_crud.config import CrudConfig
from perennia_crud.crud import CrudEngine
from perennia_crud.exceptions import ConcurrentModificationError, RecordNotFoundError
from perennia_crud.schema import EntitySchema


class FakeCursor:
    """Replays a scripted sequence of (rowcount, fetchone/fetchall) results,
    one per execute() call, so a single fake cursor can stand in for an
    entire real transaction without a database."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.rowcount = 0
        self.lastrowid = 1
        self._next_result = None
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, tuple(params)))
        resp = self._responses.pop(0)
        self.rowcount = resp.get("rowcount", 0)
        self._next_result = resp.get("result")
        if "lastrowid" in resp:
            self.lastrowid = resp["lastrowid"]

    def fetchone(self):
        return self._next_result

    def fetchall(self):
        return self._next_result or []


class FakeDatabase:
    """One shared cursor for every transaction()/cursor() call in a test,
    so bulk operations are provably running on a single connection."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def transaction(self):
        try:
            yield self._cursor
            self.commits += 1
        except Exception:
            self.rollbacks += 1
            raise

    @contextmanager
    def cursor(self):
        yield self._cursor


def _schema(**overrides):
    defaults = dict(table="widgets", fields=["name"], soft_delete=True)
    defaults.update(overrides)
    return EntitySchema(**defaults)


def _engine(fake_db, hooks=None, schema=None):
    with patch("perennia_crud.crud.Database", return_value=fake_db):
        return CrudEngine(CrudConfig(), schema or _schema(), hooks=hooks)


def test_bulk_create_is_atomic_on_success():
    row1 = {"id": 1, "name": "a"}
    row2 = {"id": 2, "name": "b"}
    cur = FakeCursor([
        {"rowcount": 1, "lastrowid": 1}, {"result": row1},
        {"rowcount": 1, "lastrowid": 2}, {"result": row2},
    ])
    db = FakeDatabase(cur)
    hooks = MagicMock()
    engine = _engine(db, hooks=hooks)

    results = engine.bulk_create([{"name": "a"}, {"name": "b"}])

    assert results == [row1, row2]
    assert db.commits == 1 and db.rollbacks == 0
    assert hooks.after_create.call_count == 2


def test_bulk_create_rolls_back_entirely_if_any_record_fails():
    row1 = {"id": 1, "name": "a"}
    cur = FakeCursor([
        {"rowcount": 1, "lastrowid": 1}, {"result": row1},   # first record ok
        {"rowcount": 1, "lastrowid": 2}, {"result": None},   # second insert "succeeds" but re-fetch finds nothing
    ])
    db = FakeDatabase(cur)
    hooks = MagicMock()
    engine = _engine(db, hooks=hooks)

    with pytest.raises(RecordNotFoundError):
        engine.bulk_create([{"name": "a"}, {"name": "b"}])

    assert db.commits == 0 and db.rollbacks == 1
    # Neither record's after_create hook should fire — the batch is
    # all-or-nothing, so the first record's success is not reported.
    hooks.after_create.assert_not_called()


def test_bulk_update_rolls_back_whole_batch_on_lost_row():
    existing1 = {"id": 1, "name": "old-a"}
    updated1 = {"id": 1, "name": "new-a"}
    existing2 = {"id": 2, "name": "old-b"}
    cur = FakeCursor([
        {"result": existing1},               # fetch existing #1
        {"rowcount": 1},                     # update #1
        {"result": updated1},                # re-fetch #1
        {"result": existing2},               # fetch existing #2
        {"rowcount": 0},                     # update #2 matched nothing (race)
    ])
    db = FakeDatabase(cur)
    hooks = MagicMock()
    engine = _engine(db, hooks=hooks)

    with pytest.raises(ConcurrentModificationError):
        engine.bulk_update([(1, {"name": "new-a"}), (2, {"name": "new-b"})])

    assert db.commits == 0 and db.rollbacks == 1
    hooks.after_update.assert_not_called()


def test_bulk_delete_is_all_or_nothing():
    existing1 = {"id": 1, "name": "a"}
    cur = FakeCursor([
        {"result": existing1},   # fetch #1
        {"rowcount": 1},         # delete #1
        {"result": None},        # fetch #2 -> missing
    ])
    db = FakeDatabase(cur)
    hooks = MagicMock()
    engine = _engine(db, hooks=hooks)

    with pytest.raises(RecordNotFoundError):
        engine.bulk_delete([1, 2])

    assert db.commits == 0 and db.rollbacks == 1
    hooks.after_delete.assert_not_called()


def test_bulk_delete_succeeds_and_counts_all_when_every_record_exists():
    existing1 = {"id": 1, "name": "a"}
    existing2 = {"id": 2, "name": "b"}
    cur = FakeCursor([
        {"result": existing1}, {"rowcount": 1},
        {"result": existing2}, {"rowcount": 1},
    ])
    db = FakeDatabase(cur)
    hooks = MagicMock()
    engine = _engine(db, hooks=hooks)

    count = engine.bulk_delete([1, 2])

    assert count == 2
    assert db.commits == 1
    assert hooks.after_delete.call_count == 2


def test_update_raises_concurrent_modification_when_row_vanishes_mid_write():
    existing = {"id": 1, "name": "a"}
    cur = FakeCursor([
        {"result": existing},   # get() before update
        {"rowcount": 0},        # update matches nothing (deleted concurrently)
    ])
    db = FakeDatabase(cur)
    engine = _engine(db)

    with pytest.raises(ConcurrentModificationError):
        engine.update(1, {"name": "b"})


def test_delete_does_not_fire_after_delete_hook_when_nothing_was_deleted():
    existing = {"id": 1, "name": "a"}
    cur = FakeCursor([
        {"result": existing},   # get() before delete
        {"rowcount": 0},        # delete matches nothing (already gone)
    ])
    db = FakeDatabase(cur)
    hooks = MagicMock()
    engine = _engine(db, hooks=hooks)

    deleted = engine.delete(1)

    assert deleted is False
    hooks.after_delete.assert_not_called()
