"""Regroupement des emprunteurs appariés en identités consolidées (union-find).

Construit le graphe implicite des paires appariées (par blocage + score) et en
extrait les composantes connexes, chacune devenant un `id_emprunteur_bic`
stable.
"""

from __future__ import annotations

from dataclasses import dataclass

from bic.identity.blocking import cles_de_blocage
from bic.identity.match import comparer
from bic.identity.normalize import normaliser_identifiant, normaliser_nom_complet


@dataclass(frozen=True)
class EmprunteurAResoudre:
    """Représentation minimale d'un emprunteur, telle que consommée par la résolution d'identité."""

    cle: str
    type_personne: str
    nom: str | None
    prenom: str | None
    raison_sociale: str | None
    date_naissance: str | None
    numero_piece: str | None
    nif: str | None


class _UnionFind:
    """Structure union-find avec compression de chemin, pour extraire les composantes connexes."""

    def __init__(self, elements: list[str]) -> None:
        self._parent = {e: e for e in elements}

    def find(self, x: str) -> str:
        racine = x
        while self._parent[racine] != racine:
            racine = self._parent[racine]
        while self._parent[x] != racine:
            self._parent[x], x = racine, self._parent[x]
        return racine

    def union(self, a: str, b: str) -> None:
        # Le représentant retenu est toujours le plus petit lexicographiquement,
        # pour que le clustering final ne dépende pas de l'ordre de traitement
        # des paires (lui-même sensible à la randomisation du hachage des `set`).
        racine_a, racine_b = self.find(a), self.find(b)
        if racine_a == racine_b:
            return
        if racine_a < racine_b:
            self._parent[racine_b] = racine_a
        else:
            self._parent[racine_a] = racine_b


def _preparer(entree: EmprunteurAResoudre) -> tuple[str, str, str]:
    """Retourne (identifiant normalisé, nom complet normalisé, date de naissance)."""
    if entree.type_personne == "PP":
        identifiant = normaliser_identifiant(entree.numero_piece)
        nom_complet = normaliser_nom_complet(entree.nom, entree.prenom)
    else:
        identifiant = normaliser_identifiant(entree.nif)
        nom_complet = normaliser_nom_complet(entree.raison_sociale)
    return identifiant, nom_complet, entree.date_naissance or ""


def resoudre_identites(entrees: list[EmprunteurAResoudre]) -> dict[str, str]:
    """Résout les identités d'une liste d'emprunteurs.

    Retourne, pour chaque `cle` d'entrée, l'`id_emprunteur_bic` stable du
    cluster auquel elle appartient. Seules les correspondances « certaine »
    et « probable » sont fusionnées ; les paires « à revoir » sont laissées
    de côté (pas de fusion automatique).
    """
    prepares = {e.cle: _preparer(e) for e in entrees}

    blocs: dict[str, list[str]] = {}
    for cle, (identifiant, nom_complet, date_naissance) in prepares.items():
        for cle_bloc in cles_de_blocage(identifiant, nom_complet, date_naissance):
            blocs.setdefault(cle_bloc, []).append(cle)

    uf = _UnionFind([e.cle for e in entrees])
    paires_evaluees: set[tuple[str, str]] = set()

    for membres in blocs.values():
        for i in range(len(membres)):
            for j in range(i + 1, len(membres)):
                a, b = membres[i], membres[j]
                paire = (a, b) if a < b else (b, a)
                if paire in paires_evaluees:
                    continue
                paires_evaluees.add(paire)

                identifiant_a, nom_a, naissance_a = prepares[a]
                identifiant_b, nom_b, naissance_b = prepares[b]
                resultat = comparer(
                    identifiant_a, nom_a, naissance_a, identifiant_b, nom_b, naissance_b
                )
                if resultat.decision in ("certaine", "probable"):
                    uf.union(a, b)

    racines_triees = sorted({uf.find(e.cle) for e in entrees})
    id_bic_par_racine = {racine: f"BIC{i + 1:08d}" for i, racine in enumerate(racines_triees)}

    return {e.cle: id_bic_par_racine[uf.find(e.cle)] for e in entrees}
