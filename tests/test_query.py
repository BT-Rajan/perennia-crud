import pytest

from perennia_crud.query import FilterCondition, SortField, ListQuery, PagedResult
from perennia_crud.exceptions import InvalidQueryError


def test_filter_condition_rejects_unknown_operator():
    with pytest.raises(InvalidQueryError):
        FilterCondition("name", "contains", "acme")


def test_filter_condition_in_requires_iterable():
    with pytest.raises(InvalidQueryError):
        FilterCondition("id", "in", 5)


def test_filter_condition_in_accepts_list():
    FilterCondition("id", "in", [1, 2, 3])  # should not raise


def test_sort_field_rejects_bad_direction():
    with pytest.raises(InvalidQueryError):
        SortField("name", "sideways")


def test_paged_result_has_more():
    result = PagedResult(items=[{}] * 20, total=45, page=1, page_size=20)
    assert result.has_more is True
    result = PagedResult(items=[{}] * 5, total=45, page=3, page_size=20)
    assert result.has_more is False
