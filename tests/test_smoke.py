"""Test de fumée : création du schéma et insertion d'un déclarant."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.orm import Session

from bic.models import Declarant, TypeEtablissement


@pytest.mark.integration
def test_create_tables_and_insert_declarant(db_session: Session) -> None:
    """Le schéma doit être créé et un déclarant doit être insérable puis relisible."""
    declarant = Declarant(
        code_declarant="BQ000001",
        raison_sociale="Banque Alpha du Sahel",
        type_etablissement=TypeEtablissement.BANQUE,
        pays="NE",
        date_agrement=datetime.date(2010, 1, 1),
    )
    db_session.add(declarant)
    db_session.commit()

    retrieved = db_session.get(Declarant, "BQ000001")

    assert retrieved is not None
    assert retrieved.raison_sociale == "Banque Alpha du Sahel"
    assert retrieved.type_etablissement == TypeEtablissement.BANQUE
