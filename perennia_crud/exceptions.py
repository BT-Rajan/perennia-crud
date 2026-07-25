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


class DuplicateRecordError(PerenniaCrudError):
    """Raised when a write violates a unique constraint (e.g. duplicate
    key). Translated from the database driver's integrity error so callers
    never need to catch a driver-specific exception type."""
    code = "duplicate_record"


class ConcurrentModificationError(PerenniaCrudError):
    """Raised when a record changes or disappears between the moment
    perennia-crud read it and the moment it tried to write to it (e.g.
    another request deleted the row first). The caller should re-fetch and
    retry, not treat this as a client input error."""
    code = "concurrent_modification"
