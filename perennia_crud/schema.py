import re
from dataclasses import dataclass, field
from typing import List, Optional

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str, what: str) -> str:
    from .exceptions import InvalidConfigurationError

    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise InvalidConfigurationError(f"Invalid {what}: '{name}'.")
    return name


@dataclass(frozen=True)
class EntitySchema:
    """Describes an existing business table. perennia-crud never creates or
    migrates tables — the consuming module owns its schema.

    fields is the allowlist of writable, filterable, sortable, and
    selectable columns. Any field not listed here is rejected, since column
    names cannot be parameterized in SQL."""

    table: str
    fields: List[str]
    primary_key: str = "id"
    soft_delete: bool = True
    soft_delete_column: str = "deleted_at"
    permission_prefix: Optional[str] = None

    def __post_init__(self):
        from .exceptions import InvalidConfigurationError

        _validate_identifier(self.table, "table name")
        _validate_identifier(self.primary_key, "primary key column")
        if self.soft_delete:
            _validate_identifier(self.soft_delete_column, "soft delete column")
        if not self.fields:
            raise InvalidConfigurationError("fields must not be empty.")
        normalized = []
        for f in self.fields:
            normalized.append(_validate_identifier(f, "field"))
        object.__setattr__(self, "fields", normalized)
        if self.primary_key in self.fields:
            raise InvalidConfigurationError(
                "primary_key must not be listed in fields (it is never user-writable)."
            )

    @property
    def permission_code_prefix(self) -> str:
        return self.permission_prefix or self.table

    def validate_fields(self, data_keys) -> None:
        from .exceptions import InvalidFieldError

        unknown = set(data_keys) - set(self.fields)
        if unknown:
            raise InvalidFieldError(
                f"Unknown field(s) for table '{self.table}': {sorted(unknown)}."
            )
