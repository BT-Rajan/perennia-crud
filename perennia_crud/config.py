from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "perennia"
    charset: str = "utf8mb4"
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0

    def __post_init__(self):
        from .exceptions import InvalidConfigurationError

        for name in ("connect_timeout", "read_timeout", "write_timeout"):
            if getattr(self, name) <= 0:
                raise InvalidConfigurationError(f"{name} must be positive.")


@dataclass(frozen=True)
class CrudConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    default_page_size: int = 20
    max_page_size: int = 100
    max_connect_retries: int = 2
    retry_backoff_seconds: float = 0.2

    def __post_init__(self):
        from .exceptions import InvalidConfigurationError

        if self.default_page_size <= 0:
            raise InvalidConfigurationError("default_page_size must be positive.")
        if self.max_page_size <= 0 or self.max_page_size < self.default_page_size:
            raise InvalidConfigurationError(
                "max_page_size must be positive and >= default_page_size."
            )
        if self.max_connect_retries < 0:
            raise InvalidConfigurationError("max_connect_retries must not be negative.")
        if self.retry_backoff_seconds < 0:
            raise InvalidConfigurationError("retry_backoff_seconds must not be negative.")
