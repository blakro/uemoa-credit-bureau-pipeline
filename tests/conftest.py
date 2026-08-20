"""Fixtures pytest partagées.

Les tests marqués ``integration`` nécessitent une base MySQL et sont
automatiquement skippés si la variable d'environnement ``MYSQL_HOST``
est absente (cas du sandbox de développement, sans MySQL disponible).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from bic.db import create_all_tables, create_db_engine, get_session_factory
from bic.models import Base


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skippe automatiquement les tests d'intégration quand MySQL n'est pas disponible."""
    if os.environ.get("MYSQL_HOST"):
        return
    skip_integration = pytest.mark.skip(
        reason="MYSQL_HOST non défini : MySQL n'est disponible qu'en CI, pas dans ce sandbox"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Fournit une session SQLAlchemy sur une base MySQL propre (schéma créé, données vidées)."""
    engine = create_db_engine()
    create_all_tables(engine)
    session_factory = get_session_factory(engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()
        engine.dispose()
