"""Agrégation des données du tableau de bord statique (docs/data/dashboard.json)."""

from __future__ import annotations

import datetime

import pandas as pd

from bic.generator.anomalies import DeclarationBrute
from bic.generator.profiles import ProfilDeclarant
from bic.reporting.solvabilite import bande_de_risque, calculer_cutoffs_bandes
from bic.validation.engine import RapportValidation

#: Champs suivis pour le calcul de la complétude déclarative.
_CHAMPS_COMPLETUDE_EMPRUNTEUR = ("identite_principale", "piece_identification", "telephone")
_CHAMPS_COMPLETUDE_CONTRAT = (
    "date_octroi",
    "date_echeance",
    "montant_octroye",
    "encours",
    "classification",
)


def _valeur_effective_emprunteur(champ: str, champs: dict[str, str]) -> str:
    if champ == "identite_principale":
        return champs["nom"] if champs["type_personne"] == "PP" else champs["raison_sociale"]
    if champ == "piece_identification":
        return champs["numero_piece"] if champs["type_personne"] == "PP" else champs["nif"]
    return champs.get(champ, "")


def _calculer_completude(declarations: list[DeclarationBrute]) -> list[dict]:
    """Calcule le taux de complétude (part des valeurs non vides) pour un jeu de champs clés."""
    compteurs = {
        champ: [0, 0] for champ in (*_CHAMPS_COMPLETUDE_EMPRUNTEUR, *_CHAMPS_COMPLETUDE_CONTRAT)
    }

    for declaration in declarations:
        for champs in declaration.emprunteurs:
            for champ in _CHAMPS_COMPLETUDE_EMPRUNTEUR:
                compteurs[champ][1] += 1
                if _valeur_effective_emprunteur(champ, champs):
                    compteurs[champ][0] += 1
        for champs in declaration.contrats:
            for champ in _CHAMPS_COMPLETUDE_CONTRAT:
                compteurs[champ][1] += 1
                if champs.get(champ):
                    compteurs[champ][0] += 1

    return [
        {"champ": champ, "taux_completude": (rempli / total if total else 1.0)}
        for champ, (rempli, total) in compteurs.items()
    ]


def _classement_declarants(
    rapports: list[RapportValidation], profils_par_code: dict[str, ProfilDeclarant]
) -> list[dict]:
    """Classe les déclarants par taux de rejet décroissant, agrégé sur tous leurs arrêtés."""
    totaux: dict[str, list[int]] = {}
    for rapport in rapports:
        rejetes, total = totaux.setdefault(rapport.code_declarant, [0, 0])
        totaux[rapport.code_declarant] = [
            rejetes + rapport.nombre_contrats_rejetes,
            total + rapport.nombre_contrats,
        ]

    classement = [
        {
            "code_declarant": code,
            "raison_sociale": profils_par_code[code].raison_sociale
            if code in profils_par_code
            else code,
            "taux_rejet": (rejetes / total if total else 0.0),
        }
        for code, (rejetes, total) in totaux.items()
    ]
    return sorted(classement, key=lambda d: d["taux_rejet"], reverse=True)


def _top_erreurs(rapports: list[RapportValidation], n: int = 10) -> list[dict]:
    """Retourne les `n` codes d'erreur les plus fréquents, tous déclarants et arrêtés confondus."""
    compteur: dict[str, int] = {}
    for rapport in rapports:
        for rejet in rapport.rejets:
            compteur[rejet.code] = compteur.get(rejet.code, 0) + 1
    top = sorted(compteur.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"code": code, "occurrences": n} for code, n in top]


def _evolution_mensuelle(
    rapports: list[RapportValidation], profils_par_code: dict[str, ProfilDeclarant]
) -> dict:
    """Taux de rejet mensuel, une série par profil de qualité déclarative."""
    arretes = sorted({rapport.date_arrete for rapport in rapports})
    profils = ("excellent", "moyen", "defaillant")

    totaux: dict[tuple[str, datetime.date], list[int]] = {}
    for rapport in rapports:
        profil = profils_par_code[rapport.code_declarant].qualite
        cle = (profil, rapport.date_arrete)
        rejetes, total = totaux.setdefault(cle, [0, 0])
        totaux[cle] = [rejetes + rapport.nombre_contrats_rejetes, total + rapport.nombre_contrats]

    series = []
    for profil in profils:
        taux = []
        for arrete in arretes:
            rejetes, total = totaux.get((profil, arrete), [0, 0])
            taux.append(rejetes / total if total else 0.0)
        series.append({"profil": profil, "taux_rejet": taux})

    return {"arretes": [a.isoformat() for a in arretes], "series": series}


def _distribution_scores(features: pd.DataFrame, scores: pd.Series, bornes_bandes: tuple) -> dict:
    """Répartition des emprunteurs par bande de risque, avec le taux de défaut observé."""
    bandes_ordre = ["A", "B", "C", "D", "E"]
    table = pd.DataFrame(
        {
            "bande": scores.map(lambda s: bande_de_risque(s, bornes_bandes)),
            "defaut": features["defaut"].to_numpy(),
        }
    )
    agrege = table.groupby("bande").agg(nb=("defaut", "count"), taux_defaut=("defaut", "mean"))
    agrege = agrege.reindex(bandes_ordre).fillna(0)

    return {
        "bandes": bandes_ordre,
        "nb_emprunteurs": agrege["nb"].astype(int).tolist(),
        "taux_defaut_observe": agrege["taux_defaut"].tolist(),
    }


def construire_donnees_dashboard(
    declarations: list[DeclarationBrute],
    rapports: list[RapportValidation],
    profiles: list[ProfilDeclarant],
    nb_emprunteurs_consolides: int,
    features: pd.DataFrame,
    scores: pd.Series,
    auc: float,
) -> dict:
    """Construit le dictionnaire JSON-sérialisable consommé par le tableau de bord statique."""
    profils_par_code = {p.code_declarant: p for p in profiles}

    total_contrats = sum(r.nombre_contrats for r in rapports)
    total_acceptes = sum(r.nombre_contrats_acceptes + r.nombre_contrats_reserve for r in rapports)
    bornes_bandes = calculer_cutoffs_bandes(scores)

    return {
        "bandeau": {
            "nb_declarations_traitees": len(rapports),
            "taux_acceptation_global": (total_acceptes / total_contrats) if total_contrats else 0.0,
            "nb_emprunteurs_consolides": nb_emprunteurs_consolides,
            "auc_modele": auc,
        },
        "classement_declarants": _classement_declarants(rapports, profils_par_code),
        "top_erreurs": _top_erreurs(rapports),
        "evolution_mensuelle": _evolution_mensuelle(rapports, profils_par_code),
        "completude_par_champ": _calculer_completude(declarations),
        "distribution_scores": _distribution_scores(features, scores, bornes_bandes),
    }
