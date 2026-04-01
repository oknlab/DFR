"""PostgreSQL backend bridge stubs for DFR."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PostgresBackendConfig:
    dsn: str
    min_size: int = 1
    max_size: int = 10


class PostgresBackend:
    """Backend facade for future psycopg3/asyncpg integration."""

    def __init__(self, config: PostgresBackendConfig) -> None:
        self.config = config

    def connection_info(self) -> dict[str, str | int]:
        return {
            "dsn": self.config.dsn,
            "min_size": self.config.min_size,
            "max_size": self.config.max_size,
        }


__all__ = ["PostgresBackend", "PostgresBackendConfig"]
