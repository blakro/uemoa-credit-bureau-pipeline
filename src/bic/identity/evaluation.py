"""Évaluation de la résolution d'identité contre une vérité-terrain.

La mesure se fait **par paires** : on compare l'ensemble des paires
d'enregistrements que le moteur a fusionnées à l'ensemble des paires qui
appartiennent réellement à la même personne. C'est la métrique standard en
résolution d'entités, car elle pénalise correctement une grosse fusion
erronée (elle crée beaucoup de fausses paires d'un coup).
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass


@dataclass(frozen=True)
class MetriquesIdentite:
    """Précision, rappel et F1 de l'appariement, mesurés au niveau des paires."""

    precision: float
    rappel: float
    f1: float
    vrais_positifs: int
    faux_positifs: int
    faux_negatifs: int
    nb_enregistrements: int
    nb_identites_predites: int
    nb_identites_reelles: int

    def as_dict(self) -> dict[str, float | int]:
        """Représentation JSON-sérialisable des métriques."""
        return {
            "precision": self.precision,
            "rappel": self.rappel,
            "f1": self.f1,
            "vrais_positifs": self.vrais_positifs,
            "faux_positifs": self.faux_positifs,
            "faux_negatifs": self.faux_negatifs,
            "nb_enregistrements": self.nb_enregistrements,
            "nb_identites_predites": self.nb_identites_predites,
            "nb_identites_reelles": self.nb_identites_reelles,
        }


def _nb_paires(taille: int) -> int:
    """Nombre de paires distinctes dans un groupe de `taille` éléments."""
    return taille * (taille - 1) // 2


def _grouper(affectations: dict[str, Hashable]) -> dict[Hashable, list[str]]:
    groupes: dict[Hashable, list[str]] = {}
    for cle, groupe in affectations.items():
        groupes.setdefault(groupe, []).append(cle)
    return groupes


def evaluer_appariement(
    predictions: dict[str, str], verite: dict[str, Hashable]
) -> MetriquesIdentite:
    """Compare les clusters prédits aux clusters réels et retourne précision/rappel/F1.

    `predictions` associe chaque clé d'enregistrement à son `id_emprunteur_bic`
    prédit ; `verite` associe la même clé à son identité réelle.
    """
    clusters_predits = _grouper(predictions)
    clusters_reels = _grouper(verite)

    vrais_positifs = 0
    faux_positifs = 0

    for membres in clusters_predits.values():
        if len(membres) < 2:
            continue
        repartition: dict[Hashable, int] = {}
        for cle in membres:
            identite = verite[cle]
            repartition[identite] = repartition.get(identite, 0) + 1
        paires_correctes = sum(_nb_paires(n) for n in repartition.values())
        vrais_positifs += paires_correctes
        faux_positifs += _nb_paires(len(membres)) - paires_correctes

    total_paires_reelles = sum(_nb_paires(len(m)) for m in clusters_reels.values())
    faux_negatifs = total_paires_reelles - vrais_positifs

    precision = (
        vrais_positifs / (vrais_positifs + faux_positifs) if vrais_positifs + faux_positifs else 1.0
    )
    rappel = (
        vrais_positifs / (vrais_positifs + faux_negatifs) if vrais_positifs + faux_negatifs else 1.0
    )
    f1 = 2 * precision * rappel / (precision + rappel) if precision + rappel else 0.0

    return MetriquesIdentite(
        precision=precision,
        rappel=rappel,
        f1=f1,
        vrais_positifs=vrais_positifs,
        faux_positifs=faux_positifs,
        faux_negatifs=faux_negatifs,
        nb_enregistrements=len(predictions),
        nb_identites_predites=len(clusters_predits),
        nb_identites_reelles=len(clusters_reels),
    )


def distribution_taille_clusters(predictions: dict[str, str]) -> dict[int, int]:
    """Compte les identités consolidées par nombre d'enregistrements regroupés.

    Une identité de taille 1 n'est déclarée que par un seul établissement ;
    une identité de taille 3 est un emprunteur connu de trois déclarants.
    """
    distribution: dict[int, int] = {}
    for membres in _grouper(predictions).values():
        distribution[len(membres)] = distribution.get(len(membres), 0) + 1
    return dict(sorted(distribution.items()))
