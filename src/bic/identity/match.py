"""Score composite d'appariement entre deux emprunteurs, et règle de décision.

Règle : correspondance certaine si le numéro de pièce (ou NIF) est identique ;
probable si le score de similarité de nom est ≥ 88 et la date de naissance
identique ; à revoir entre 75 et 88 ; sans lien sinon.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

SEUIL_PROBABLE = 88
SEUIL_A_REVOIR = 75


@dataclass(frozen=True)
class ResultatAppariement:
    """Résultat de la comparaison d'une paire d'emprunteurs normalisés."""

    decision: str
    score: float


def comparer(
    identifiant_a: str,
    nom_complet_a: str,
    date_naissance_a: str,
    identifiant_b: str,
    nom_complet_b: str,
    date_naissance_b: str,
) -> ResultatAppariement:
    """Compare deux emprunteurs normalisés et retourne la décision d'appariement."""
    if identifiant_a and identifiant_b and identifiant_a == identifiant_b:
        return ResultatAppariement("certaine", 100.0)

    if not nom_complet_a or not nom_complet_b:
        return ResultatAppariement("aucune", 0.0)

    score = fuzz.token_sort_ratio(nom_complet_a, nom_complet_b)
    meme_naissance = bool(date_naissance_a) and date_naissance_a == date_naissance_b

    if score >= SEUIL_PROBABLE and meme_naissance:
        return ResultatAppariement("probable", score)
    if SEUIL_A_REVOIR <= score < SEUIL_PROBABLE:
        return ResultatAppariement("a_revoir", score)
    return ResultatAppariement("aucune", score)
