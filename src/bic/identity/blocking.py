"""Clés de blocage : limitent les comparaisons de paires à des candidats plausibles.

Sans blocage, résoudre N emprunteurs demanderait de comparer toutes les
paires (O(N²)), infaisable à l'échelle d'un BIC. On ne compare que les
emprunteurs qui partagent au moins une clé de blocage.
"""

from __future__ import annotations

import re

_VOYELLES = re.compile(r"[AEIOUY]")
_CONSONNES_REPETEES = re.compile(r"(.)\1+")
#: Substitutions phonétiques usuelles (consonnes équivalentes à l'oreille).
_EQUIVALENCES = (("PH", "F"), ("Q", "K"), ("C", "K"))


def cle_phonetique_simplifiee(mot: str) -> str:
    """Clé phonétique légère (substitut sans dépendance à un métaphone complet).

    Conserve la première lettre, harmonise quelques consonnes équivalentes,
    retire les voyelles internes et compresse les consonnes répétées, afin de
    regrouper des variantes orthographiques proches (ex. « Boubacar » et
    « Boubakar » donnent la même clé).
    """
    if not mot:
        return ""
    for motif, remplacement in _EQUIVALENCES:
        mot = mot.replace(motif, remplacement)
    premiere, reste = mot[0], mot[1:]
    sans_voyelles = _VOYELLES.sub("", reste)
    return premiere + _CONSONNES_REPETEES.sub(r"\1", sans_voyelles)


def cles_de_blocage(identifiant: str, nom_complet: str, date_naissance: str) -> set[str]:
    """Retourne les clés de blocage d'un emprunteur normalisé.

    Trois stratégies combinées : (a) numéro de pièce ou NIF normalisé,
    (b) date de naissance + première lettre du nom, (c) clé phonétique du
    premier mot du nom + année de naissance.
    """
    cles: set[str] = set()
    if identifiant:
        cles.add(f"PIECE:{identifiant}")

    premier_mot = nom_complet.split()[0] if nom_complet else ""
    if premier_mot and date_naissance:
        cles.add(f"NAISS:{date_naissance}:{premier_mot[0]}")
        cles.add(f"PHON:{cle_phonetique_simplifiee(premier_mot)}:{date_naissance[:4]}")

    return cles
