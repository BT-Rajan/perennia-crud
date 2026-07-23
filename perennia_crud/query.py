from dataclasses import dataclass, field
from typing import Any, List, Optional

VALID_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "like", "in"}


@dataclass(frozen=True)
class FilterCondition:
    field: str
    operator: str
    value: Any

    def __post_init__(self):
        from .exceptions import InvalidQueryError

        if self.operator not in VALID_OPERATORS:
            raise InvalidQueryError(f"Unsupported filter operator: '{self.operator}'.")
        if self.operator == "in" and not isinstance(self.value, (list, tuple, set)):
            raise InvalidQueryError("'in' operator requires a list/tuple/set value.")


@dataclass(frozen=True)
class SortField:
    field: str
    direction: str = "asc"

    def __post_init__(self):
        from .exceptions import InvalidQueryError

        if self.direction.lower() not in ("asc", "desc"):
            raise InvalidQueryError(f"Unsupported sort direction: '{self.direction}'.")


@dataclass(frozen=True)
class ListQuery:
    filters: List[FilterCondition] = field(default_factory=list)
    sort: List[SortField] = field(default_factory=list)
    page: int = 1
    page_size: Optional[int] = None
    fields: Optional[List[str]] = None  # None = all schema fields + primary key
    include_deleted: bool = False


@dataclass(frozen=True)
class PagedResult:
    items: List[dict]
    total: int
    page: int
    page_size: int

    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total
