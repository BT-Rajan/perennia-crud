import logging
from typing import Any, List, Optional, Tuple

from .config import CrudConfig
from .db import Database
from .engine import query_builder
from .exceptions import ConcurrentModificationError, RecordNotFoundError
from .query import ListQuery, PagedResult
from .schema import EntitySchema

logger = logging.getLogger("perennia_crud")


class CrudEngine:
    """Public API. Small, predictable surface: create, get, exists, update,
    delete, restore, list, and bulk_* variants — reused as-is by every
    business module's data operations.

    access: optional perennia-access PerenniaAccess instance (or any object
    exposing .require(identity, permission_code)). When provided, every
    operation enforces '<entity.permission_code_prefix>.<action>' first.
    perennia-crud never maintains its own RBAC.

    hooks: optional object exposing any of before_create, after_create,
    before_update, after_update, before_delete, after_delete, before_restore,
    after_restore. perennia-crud calls whichever are present; it never knows
    or cares what they do. Business logic stays in the consuming module.

    bulk_* methods run as a single database transaction: all records
    succeed or none do. If any record in the batch is missing, or another
    request modifies it mid-batch, the whole batch is rolled back and a
    RecordNotFoundError / ConcurrentModificationError is raised — callers
    that need best-effort/partial-success semantics should loop over the
    single-record methods themselves instead.
    """

    def __init__(self, config: CrudConfig, entity: EntitySchema,
                 access: Optional[object] = None, hooks: Optional[object] = None):
        self._config = config
        self._db = Database(
            config.database,
            max_connect_retries=config.max_connect_retries,
            retry_backoff_seconds=config.retry_backoff_seconds,
        )
        self._entity = entity
        self._access = access
        self._hooks = hooks

    # ------------------------------------------------------------- internal

    def _authorize(self, identity, action: str) -> None:
        if self._access is not None:
            self._access.require(identity, f"{self._entity.permission_code_prefix}.{action}")

    def _call_hook(self, name: str, *args) -> None:
        hook = getattr(self._hooks, name, None) if self._hooks is not None else None
        if hook is not None:
            hook(*args)

    def _page_size(self, requested: Optional[int]) -> int:
        size = requested or self._config.default_page_size
        return min(size, self._config.max_page_size)

    def _fetch(self, cur, record_id: Any, include_deleted: bool) -> dict:
        """Fetch a record using an already-open cursor, so callers building
        a multi-statement transaction (bulk_* methods) stay on one
        connection instead of opening a new one per read."""
        sql, params = query_builder.build_get(self._entity, record_id, include_deleted)
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        if not row:
            raise RecordNotFoundError(
                f"Record '{record_id}' was not found in '{self._entity.table}'."
            )
        return row

    def _not_matched_error(self, record_id: Any) -> ConcurrentModificationError:
        return ConcurrentModificationError(
            f"Record '{record_id}' in '{self._entity.table}' was modified or removed "
            f"by another operation before this write could apply."
        )

    # ------------------------------------------------------------------ get

    def get(self, record_id: Any, identity=None, include_deleted: bool = False) -> dict:
        self._authorize(identity, "read")
        with self._db.cursor() as cur:
            return self._fetch(cur, record_id, include_deleted)

    def exists(self, record_id: Any, identity=None, include_deleted: bool = False) -> bool:
        self._authorize(identity, "read")
        sql, params = query_builder.build_exists(self._entity, record_id, include_deleted)
        with self._db.cursor() as cur:
            cur.execute(sql, tuple(params))
            return cur.fetchone() is not None

    def list(self, query: ListQuery, identity=None) -> PagedResult:
        self._authorize(identity, "read")
        page_size = self._page_size(query.page_size)
        offset = (max(query.page, 1) - 1) * page_size

        select_sql, select_params, count_sql, count_params = query_builder.build_list(
            self._entity, query, offset, page_size
        )
        with self._db.cursor() as cur:
            cur.execute(select_sql, tuple(select_params))
            items = cur.fetchall()
            cur.execute(count_sql, tuple(count_params))
            total = cur.fetchone()["total"]

        return PagedResult(items=items, total=total, page=max(query.page, 1), page_size=page_size)

    # --------------------------------------------------------------- create

    def create(self, data: dict, identity=None) -> dict:
        self._authorize(identity, "create")
        self._call_hook("before_create", data)

        sql, params = query_builder.build_insert(self._entity, data)
        with self._db.transaction() as cur:
            cur.execute(sql, tuple(params))
            record_id = data.get(self._entity.primary_key, cur.lastrowid)
            record = self._fetch(cur, record_id, include_deleted=True)

        self._call_hook("after_create", record)
        return record

    def bulk_create(self, records: List[dict], identity=None) -> List[dict]:
        """Inserts every record in one transaction. If any insert fails
        (including a duplicate-key violation), none of the records are
        persisted."""
        self._authorize(identity, "create")
        if not records:
            return []

        results = []
        with self._db.transaction() as cur:
            for data in records:
                self._call_hook("before_create", data)
                sql, params = query_builder.build_insert(self._entity, data)
                cur.execute(sql, tuple(params))
                record_id = data.get(self._entity.primary_key, cur.lastrowid)
                results.append(self._fetch(cur, record_id, include_deleted=True))

        for record in results:
            self._call_hook("after_create", record)
        return results

    # --------------------------------------------------------------- update

    def update(self, record_id: Any, data: dict, identity=None) -> dict:
        self._authorize(identity, "update")
        existing = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("before_update", existing, data)

        sql, params = query_builder.build_update(self._entity, record_id, data)
        with self._db.transaction() as cur:
            cur.execute(sql, tuple(params))
            if cur.rowcount == 0:
                # existing was confirmed present moments ago; zero rows
                # matched now means it was deleted concurrently.
                raise self._not_matched_error(record_id)

        record = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("after_update", record)
        return record

    def bulk_update(self, updates: List[Tuple[Any, dict]], identity=None) -> List[dict]:
        """updates is a list of (record_id, data) tuples. Applied in one
        transaction: if any record is missing or is removed by another
        request mid-batch, none of the updates are persisted."""
        self._authorize(identity, "update")
        if not updates:
            return []

        results = []
        with self._db.transaction() as cur:
            for record_id, data in updates:
                existing = self._fetch(cur, record_id, include_deleted=True)
                self._call_hook("before_update", existing, data)
                sql, params = query_builder.build_update(self._entity, record_id, data)
                cur.execute(sql, tuple(params))
                if cur.rowcount == 0:
                    raise self._not_matched_error(record_id)
                results.append(self._fetch(cur, record_id, include_deleted=True))

        for record in results:
            self._call_hook("after_update", record)
        return results

    # --------------------------------------------------------------- delete

    def delete(self, record_id: Any, identity=None) -> bool:
        self._authorize(identity, "delete")
        existing = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("before_delete", existing)

        if self._entity.soft_delete:
            sql, params = query_builder.build_soft_delete(self._entity, record_id)
        else:
            sql, params = query_builder.build_hard_delete(self._entity, record_id)
        with self._db.transaction() as cur:
            cur.execute(sql, tuple(params))
            deleted = cur.rowcount > 0

        if deleted:
            self._call_hook("after_delete", existing)
        return deleted

    def bulk_delete(self, record_ids: List[Any], identity=None) -> int:
        """Deletes every record in one transaction. All-or-nothing: if any
        id is missing or already deleted, the whole batch is rolled back
        and RecordNotFoundError is raised, rather than silently deleting a
        partial subset as a per-record loop would."""
        self._authorize(identity, "delete")
        if not record_ids:
            return 0

        deleted_records = []
        with self._db.transaction() as cur:
            for record_id in record_ids:
                existing = self._fetch(cur, record_id, include_deleted=True)
                self._call_hook("before_delete", existing)
                if self._entity.soft_delete:
                    sql, params = query_builder.build_soft_delete(self._entity, record_id)
                else:
                    sql, params = query_builder.build_hard_delete(self._entity, record_id)
                cur.execute(sql, tuple(params))
                if cur.rowcount == 0:
                    raise self._not_matched_error(record_id)
                deleted_records.append(existing)

        for existing in deleted_records:
            self._call_hook("after_delete", existing)
        return len(deleted_records)

    # -------------------------------------------------------------- restore

    def restore(self, record_id: Any, identity=None) -> dict:
        self._authorize(identity, "restore")
        if not self._entity.soft_delete:
            raise RecordNotFoundError(
                f"'{self._entity.table}' does not support soft delete/restore."
            )
        existing = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("before_restore", existing)

        sql, params = query_builder.build_restore(self._entity, record_id)
        with self._db.transaction() as cur:
            cur.execute(sql, tuple(params))
            if cur.rowcount == 0:
                raise self._not_matched_error(record_id)

        record = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("after_restore", record)
        return record

    def bulk_restore(self, record_ids: List[Any], identity=None) -> List[dict]:
        """Restores every record in one transaction. All-or-nothing, same
        semantics as bulk_delete."""
        self._authorize(identity, "restore")
        if not self._entity.soft_delete:
            raise RecordNotFoundError(
                f"'{self._entity.table}' does not support soft delete/restore."
            )
        if not record_ids:
            return []

        results = []
        with self._db.transaction() as cur:
            for record_id in record_ids:
                existing = self._fetch(cur, record_id, include_deleted=True)
                self._call_hook("before_restore", existing)
                sql, params = query_builder.build_restore(self._entity, record_id)
                cur.execute(sql, tuple(params))
                if cur.rowcount == 0:
                    raise self._not_matched_error(record_id)
                results.append(self._fetch(cur, record_id, include_deleted=True))

        for record in results:
            self._call_hook("after_restore", record)
        return results
