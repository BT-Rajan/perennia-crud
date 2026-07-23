import pytest

from perennia_crud.schema import EntitySchema
from perennia_crud.exceptions import InvalidConfigurationError, InvalidFieldError


def test_valid_schema():
    schema = EntitySchema(table="customers", fields=["name", "email"])
    assert schema.permission_code_prefix == "customers"


def test_rejects_invalid_table_name():
    with pytest.raises(InvalidConfigurationError):
        EntitySchema(table="customers; DROP TABLE x", fields=["name"])


def test_rejects_invalid_field_name():
    with pytest.raises(InvalidConfigurationError):
        EntitySchema(table="customers", fields=["name; --"])


def test_rejects_empty_fields():
    with pytest.raises(InvalidConfigurationError):
        EntitySchema(table="customers", fields=[])


def test_rejects_primary_key_in_fields():
    with pytest.raises(InvalidConfigurationError):
        EntitySchema(table="customers", fields=["id", "name"], primary_key="id")


def test_custom_permission_prefix():
    schema = EntitySchema(table="tbl_customers", fields=["name"], permission_prefix="customer")
    assert schema.permission_code_prefix == "customer"


def test_validate_fields_rejects_unknown_field():
    schema = EntitySchema(table="customers", fields=["name", "email"])
    with pytest.raises(InvalidFieldError):
        schema.validate_fields(["name", "ssn"])


def test_validate_fields_accepts_known_fields():
    schema = EntitySchema(table="customers", fields=["name", "email"])
    schema.validate_fields(["name", "email"])  # should not raise
