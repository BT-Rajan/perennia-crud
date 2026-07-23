import logging
from typing import Any, List, Optional

from .config import CrudConfig
from .db import Database
from .engine import query_builder
from .exceptions import RecordNotFoundError
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
    """

    def __init__(self, config: CrudConfig, entity: EntitySchema,
                 access: Optional[object] = None, hooks: Optional[object] = None):
        self._config = config
        self._db = Database(config.database)
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

    # ------------------------------------------------------------------ get

    def get(self, record_id: Any, identity=None, include_deleted: bool = False) -> dict:
        self._authorize(identity, "read")
        sql, params = query_builder.build_get(self._entity, record_id, include_deleted)
        with self._db.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
        if not row:
            raise RecordNotFoundError(
                f"Record '{record_id}' was not found in '{self._entity.table}'."
            )
        return row

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

        record = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("after_create", record)
        return record

    def bulk_create(self, records: List[dict], identity=None) -> List[dict]:
        return [self.create(record, identity=identity) for record in records]

    # --------------------------------------------------------------- update

    def update(self, record_id: Any, data: dict, identity=None) -> dict:
        self._authorize(identity, "update")
        existing = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("before_update", existing, data)

        sql, params = query_builder.build_update(self._entity, record_id, data)
        with self._db.transaction() as cur:
            cur.execute(sql, tuple(params))

        record = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("after_update", record)
        return record

    def bulk_update(self, updates: List[tuple], identity=None) -> List[dict]:
        """updates is a list of (record_id, data) tuples."""
        return [self.update(record_id, data, identity=identity) for record_id, data in updates]

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

        self._call_hook("after_delete", existing)
        return deleted

    def bulk_delete(self, record_ids: List[Any], identity=None) -> int:
        return sum(1 for record_id in record_ids if self.delete(record_id, identity=identity))

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

        record = self.get(record_id, identity=identity, include_deleted=True)
        self._call_hook("after_restore", record)
        return record

    def bulk_restore(self, record_ids: List[Any], identity=None) -> List[dict]:
        return [self.restore(record_id, identity=identity) for record_id in record_ids]
