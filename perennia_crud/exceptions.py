class PerenniaCrudError(Exception):
    """Base error. Safe to show a generic message to clients."""
    code = "crud_error"


class InvalidConfigurationError(PerenniaCrudError):
    code = "invalid_configuration"


class InvalidFieldError(PerenniaCrudError):
    code = "invalid_field"


class InvalidQueryError(PerenniaCrudError):
    code = "invalid_query"


class RecordNotFoundError(PerenniaCrudError):
    code = "record_not_found"


class ValidationError(PerenniaCrudError):
    code = "validation_error"


class CrudDatabaseError(PerenniaCrudError):
    code = "crud_database_error"
