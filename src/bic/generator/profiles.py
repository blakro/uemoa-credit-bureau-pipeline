"""Profils des déclarants synthétiques et leurs taux d'anomalie cibles.

Douze déclarants fictifs (aucun établissement réel) répartis en trois
profils de qualité déclarative : ``excellent`` (1 % d'anomalies),
``moyen`` (8 %) et ``defaillant`` (25 %). Cette vérité-terrain sert à
rendre lisible le dashboard de qualité en phase 6.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

#: Taux d'anomalie cible par profil de qualité déclarative.
TAUX_ANOMALIE_PAR_PROFIL: dict[str, float] = {
    "excellent": 0.01,
    "moyen": 0.08,
    "defaillant": 0.25,
}


@dataclass(frozen=True)
class ProfilDeclarant:
    """Profil synthétique d'un déclarant assujetti."""

    code_declarant: str
    raison_sociale: str
    type_etablissement: str
    pays: str
    date_agrement: datetime.date
    qualite: str

    @property
    def taux_anomalie(self) -> float:
        """Taux d'anomalie cible pour ce déclarant, dérivé de son profil de qualité."""
        return TAUX_ANOMALIE_PAR_PROFIL[self.qualite]


#: Les 12 déclarants synthétiques, répartis 3 excellents / 6 moyens / 3 défaillants.
_DEFINITIONS: tuple[tuple[str, str, str, str, str], ...] = (
    ("BQ000001", "Banque Alpha du Sahel", "banque", "NE", "excellent"),
    ("BQ000002", "Banque Zénith du Niger", "banque", "NE", "excellent"),
    ("EF000001", "EF Béta Finances", "etablissement_financier", "NE", "excellent"),
    ("BQ000003", "Banque Concorde UEMOA", "banque", "NE", "moyen"),
    ("BQ000004", "Banque Horizon Sahélien", "banque", "NE", "moyen"),
    ("BQ000005", "Banque Étoile du Fleuve", "banque", "NE", "moyen"),
    ("EF000002", "EF Gamma Crédit", "etablissement_financier", "NE", "moyen"),
    ("EF000003", "EF Delta Investissement", "etablissement_financier", "NE", "moyen"),
    ("SF000001", "SFD Espoir Niamey", "sfd", "NE", "moyen"),
    ("BQ000006", "Banque Oméga du Ténéré", "banque", "NE", "defaillant"),
    ("EF000004", "EF Kappa Services", "etablissement_financier", "NE", "defaillant"),
    ("SF000002", "SFD Solidarité Rurale", "sfd", "NE", "defaillant"),
)


def get_declarant_profiles() -> list[ProfilDeclarant]:
    """Retourne la liste des 12 profils de déclarants synthétiques."""
    date_agrement = datetime.date(2012, 1, 1)
    return [
        ProfilDeclarant(
            code_declarant=code,
            raison_sociale=raison_sociale,
            type_etablissement=type_etablissement,
            pays=pays,
            date_agrement=date_agrement,
            qualite=qualite,
        )
        for code, raison_sociale, type_etablissement, pays, qualite in _DEFINITIONS
    ]
