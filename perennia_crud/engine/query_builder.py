"""Parameterized SQL construction for a single EntitySchema. Isolated so the
persistence approach can evolve without touching CrudEngine's public API.

Column and table names are never taken from filter/query values directly —
they are validated against the schema's field allowlist first. Only values
are passed as bind parameters."""
from typing import Any, List, Tuple

from ..exceptions import InvalidFieldError, InvalidQueryError
from ..query import FilterCondition, ListQuery, SortField
from ..schema import EntitySchema

_OPERATOR_SQL = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
}


def _selectable_columns(schema: EntitySchema, fields) -> List[str]:
    if fields is None:
        columns = list(schema.fields)
    else:
        unknown = set(fields) - set(schema.fields)
        if unknown:
            raise InvalidFieldError(f"Unknown selectable field(s): {sorted(unknown)}.")
        columns = list(fields)
    return [schema.primary_key] + [c for c in columns if c != schema.primary_key]


def _validate_condition_field(schema: EntitySchema, field_name: str) -> None:
    if field_name != schema.primary_key and field_name not in schema.fields:
        raise InvalidFieldError(f"Unknown field '{field_name}' for table '{schema.table}'.")


def _where_clause(schema: EntitySchema, filters: List[FilterCondition],
                   include_deleted: bool) -> Tuple[str, list]:
    clauses = []
    params: list = []

    for condition in filters:
        _validate_condition_field(schema, condition.field)
        if condition.operator == "in":
            values = list(condition.value)
            if not values:
                clauses.append("1 = 0")  # empty IN() matches nothing
                continue
            placeholders = ", ".join(["%s"] * len(values))
            clauses.append(f"{condition.field} IN ({placeholders})")
            params.extend(values)
        elif condition.operator == "like":
            clauses.append(f"{condition.field} LIKE %s")
            params.append(condition.value)
        else:
            op = _OPERATOR_SQL[condition.operator]
            clauses.append(f"{condition.field} {op} %s")
            params.append(condition.value)

    if schema.soft_delete and not include_deleted:
        clauses.append(f"{schema.soft_delete_column} IS NULL")

    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where_sql, params


def _order_clause(schema: EntitySchema, sort: List[SortField]) -> str:
    if not sort:
        return f" ORDER BY {schema.primary_key} DESC"
    parts = []
    for s in sort:
        _validate_condition_field(schema, s.field)
        parts.append(f"{s.field} {s.direction.upper()}")
    return " ORDER BY " + ", ".join(parts)


def build_list(schema: EntitySchema, query: ListQuery, offset: int, limit: int
               ) -> Tuple[str, list, str, list]:
    columns = _selectable_columns(schema, query.fields)
    column_sql = ", ".join(columns)
    where_sql, where_params = _where_clause(schema, query.filters, query.include_deleted)
    order_sql = _order_clause(schema, query.sort)

    select_sql = (
        f"SELECT {column_sql} FROM {schema.table}{where_sql}{order_sql} "
        f"LIMIT %s OFFSET %s"
    )
    select_params = where_params + [limit, offset]

    count_sql = f"SELECT COUNT(*) AS total FROM {schema.table}{where_sql}"
    count_params = list(where_params)

    return select_sql, select_params, count_sql, count_params


def build_get(schema: EntitySchema, record_id: Any, include_deleted: bool,
              fields=None) -> Tuple[str, list]:
    columns = _selectable_columns(schema, fields)
    column_sql = ", ".join(columns)
    where_sql, params = _where_clause(
        schema, [FilterCondition(schema.primary_key, "eq", record_id)], include_deleted
    )
    return f"SELECT {column_sql} FROM {schema.table}{where_sql} LIMIT 1", params


def build_exists(schema: EntitySchema, record_id: Any, include_deleted: bool) -> Tuple[str, list]:
    where_sql, params = _where_clause(
        schema, [FilterCondition(schema.primary_key, "eq", record_id)], include_deleted
    )
    return f"SELECT 1 FROM {schema.table}{where_sql} LIMIT 1", params


def build_insert(schema: EntitySchema, data: dict) -> Tuple[str, list]:
    schema.validate_fields(data.keys())
    if not data:
        raise InvalidQueryError("Cannot insert an empty record.")
    columns = list(data.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    return f"INSERT INTO {schema.table} ({column_sql}) VALUES ({placeholders})", list(data.values())


def build_update(schema: EntitySchema, record_id: Any, data: dict) -> Tuple[str, list]:
    schema.validate_fields(data.keys())
    if not data:
        raise InvalidQueryError("Cannot update with an empty record.")
    set_sql = ", ".join(f"{col} = %s" for col in data.keys())
    params = list(data.values()) + [record_id]
    return f"UPDATE {schema.table} SET {set_sql} WHERE {schema.primary_key} = %s", params


def build_soft_delete(schema: EntitySchema, record_id: Any) -> Tuple[str, list]:
    return (
        f"UPDATE {schema.table} SET {schema.soft_delete_column} = NOW(6) "
        f"WHERE {schema.primary_key} = %s",
        [record_id],
    )


def build_restore(schema: EntitySchema, record_id: Any) -> Tuple[str, list]:
    return (
        f"UPDATE {schema.table} SET {schema.soft_delete_column} = NULL "
        f"WHERE {schema.primary_key} = %s",
        [record_id],
    )


def build_hard_delete(schema: EntitySchema, record_id: Any) -> Tuple[str, list]:
    return f"DELETE FROM {schema.table} WHERE {schema.primary_key} = %s", [record_id]
