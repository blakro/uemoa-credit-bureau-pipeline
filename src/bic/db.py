"""Moteur SQLAlchemy, fabrique de sessions et création du schéma."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from bic.config import load_database_config
from bic.models import Base


def create_db_engine(url: str | None = None) -> Engine:
    """Crée le moteur SQLAlchemy à partir de l'URL fournie, ou de la config d'environnement."""
    if url is None:
        url = load_database_config().sqlalchemy_url
    return create_engine(url, pool_pre_ping=True)


def create_all_tables(engine: Engine) -> None:
    """Crée toutes les tables du schéma BIC si elles n'existent pas déjà."""
    Base.metadata.create_all(engine)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Retourne une fabrique de sessions liée au moteur donné."""
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Fournit une session transactionnelle : commit en sortie normale, rollback sur exception."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
