import pytest

from perennia_crud.schema import EntitySchema
from perennia_crud.query import FilterCondition, SortField, ListQuery
from perennia_crud.exceptions import InvalidFieldError, InvalidQueryError
from perennia_crud.engine import query_builder as qb

SCHEMA = EntitySchema(table="customers", fields=["name", "email"], soft_delete=True)
NO_SOFT_DELETE_SCHEMA = EntitySchema(table="logs", fields=["message"], soft_delete=False)


def test_build_insert_uses_only_allowed_fields():
    sql, params = qb.build_insert(SCHEMA, {"name": "Acme", "email": "a@acme.example"})
    assert "INSERT INTO customers" in sql
    assert "name" in sql and "email" in sql
    assert params == ["Acme", "a@acme.example"]


def test_build_insert_rejects_unknown_field():
    with pytest.raises(InvalidFieldError):
        qb.build_insert(SCHEMA, {"name": "Acme", "ssn": "123-45-6789"})


def test_build_insert_rejects_empty_data():
    with pytest.raises(InvalidQueryError):
        qb.build_insert(SCHEMA, {})


def test_build_update_targets_primary_key():
    sql, params = qb.build_update(SCHEMA, 42, {"name": "New Name"})
    assert "UPDATE customers SET name = %s WHERE id = %s" == sql
    assert params == ["New Name", 42]


def test_build_soft_delete_sets_deleted_at():
    sql, params = qb.build_soft_delete(SCHEMA, 42)
    assert "deleted_at = NOW(6)" in sql
    assert params == [42]


def test_build_hard_delete_for_non_soft_delete_schema():
    sql, params = qb.build_hard_delete(NO_SOFT_DELETE_SCHEMA, 7)
    assert sql == "DELETE FROM logs WHERE id = %s"
    assert params == [7]


def test_build_get_excludes_soft_deleted_by_default():
    sql, params = qb.build_get(SCHEMA, 1, include_deleted=False)
    assert "deleted_at IS NULL" in sql
    assert params == [1]


def test_build_get_includes_soft_deleted_when_requested():
    sql, params = qb.build_get(SCHEMA, 1, include_deleted=True)
    assert "deleted_at" not in sql


def test_build_list_applies_filters_sort_and_pagination():
    query = ListQuery(
        filters=[FilterCondition("name", "like", "%acme%")],
        sort=[SortField("name", "desc")],
        page=2,
    )
    select_sql, select_params, count_sql, count_params = qb.build_list(SCHEMA, query, offset=20, limit=20)
    assert "name LIKE %s" in select_sql
    assert "ORDER BY name DESC" in select_sql
    assert "LIMIT %s OFFSET %s" in select_sql
    assert select_params == ["%acme%", 20, 20]
    assert "COUNT(*)" in count_sql
    assert count_params == ["%acme%"]


def test_build_list_rejects_unknown_filter_field():
    query = ListQuery(filters=[FilterCondition("ssn", "eq", "123")])
    with pytest.raises(InvalidFieldError):
        qb.build_list(SCHEMA, query, offset=0, limit=20)


def test_build_list_in_operator_with_empty_list_matches_nothing():
    query = ListQuery(filters=[FilterCondition("name", "in", [])])
    select_sql, select_params, _, _ = qb.build_list(SCHEMA, query, offset=0, limit=20)
    assert "1 = 0" in select_sql
