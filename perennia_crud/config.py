from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "perennia"
    charset: str = "utf8mb4"


@dataclass(frozen=True)
class CrudConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    default_page_size: int = 20
    max_page_size: int = 100

    def __post_init__(self):
        from .exceptions import InvalidConfigurationError

        if self.default_page_size <= 0:
            raise InvalidConfigurationError("default_page_size must be positive.")
        if self.max_page_size <= 0 or self.max_page_size < self.default_page_size:
            raise InvalidConfigurationError(
                "max_page_size must be positive and >= default_page_size."
            )
