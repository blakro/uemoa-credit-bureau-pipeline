"""Lecture des variables d'environnement et construction de l'URL SQLAlchemy."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConfig:
    """Paramètres de connexion à la base MySQL."""

    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def sqlalchemy_url(self) -> str:
        """URL de connexion SQLAlchemy (dialecte MySQL, driver PyMySQL)."""
        return (
            f"mysql+pymysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        )


def load_database_config() -> DatabaseConfig:
    """Construit la configuration base de données à partir des variables d'environnement."""
    return DatabaseConfig(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ.get("MYSQL_DATABASE", "bic_test"),
    )
