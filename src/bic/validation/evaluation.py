"""Évaluation du moteur de validation contre la vérité-terrain des anomalies injectées.

Le générateur journalise chaque anomalie qu'il injecte volontairement. On peut
donc mesurer le **rappel** du moteur : quelle part des défauts réellement
présents a-t-il su détecter, globalement et code par code.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from bic.generator.anomalies import AnomalieInjectee
from bic.validation.engine import RapportValidation

#: Signature d'une anomalie : (déclarant, entité, ligne, champ, code).
Signature = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class MetriquesValidation:
    """Rappel du moteur de validation, global et par code d'erreur."""

    rappel_global: float
    total_anomalies: int
    total_detectees: int
    #: code -> (nombre détecté, nombre injecté)
    rappel_par_code: dict[str, tuple[int, int]]

    def as_dict(self) -> dict:
        """Représentation JSON-sérialisable des métriques."""
        return {
            "rappel_global": self.rappel_global,
            "total_anomalies": self.total_anomalies,
            "total_detectees": self.total_detectees,
            "par_code": [
                {
                    "code": code,
                    "detectees": detectees,
                    "injectees": injectees,
                    "rappel": detectees / injectees if injectees else 0.0,
                }
                for code, (detectees, injectees) in sorted(self.rappel_par_code.items())
            ],
        }


def _signatures_verite(journal: Iterable[AnomalieInjectee]) -> set[Signature]:
    return {(a.code_declarant, a.entite, a.ligne, a.champ, a.code) for a in journal}


def _signatures_detectees(rapports: Iterable[RapportValidation]) -> set[Signature]:
    return {
        (r.code_declarant, rejet.entite, rejet.identifiant, rejet.champ, rejet.code)
        for r in rapports
        for rejet in r.rejets
    }


def evaluer_detection(
    journal: Iterable[AnomalieInjectee], rapports: Iterable[RapportValidation]
) -> MetriquesValidation:
    """Mesure le rappel du moteur : part des anomalies injectées effectivement détectées."""
    verite = _signatures_verite(journal)
    detectees = _signatures_detectees(rapports)
    vrais_positifs = verite & detectees

    par_code: dict[str, tuple[int, int]] = {}
    for signature in verite:
        code = signature[4]
        detectees_code, total_code = par_code.get(code, (0, 0))
        par_code[code] = (
            detectees_code + (1 if signature in vrais_positifs else 0),
            total_code + 1,
        )

    return MetriquesValidation(
        rappel_global=len(vrais_positifs) / len(verite) if verite else 1.0,
        total_anomalies=len(verite),
        total_detectees=len(vrais_positifs),
        rappel_par_code=par_code,
    )
