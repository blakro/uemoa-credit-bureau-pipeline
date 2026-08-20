"""Agrégation des données du tableau de bord statique (docs/data/dashboard.json).

Le payload produit ici est la seule source de vérité du tableau de bord : toutes
les métriques affichées en ligne (qualité déclarative, résolution d'identité,
performance du modèle) sont recalculées à chaque exécution du pipeline, jamais
saisies à la main.
"""

from __future__ import annotations

import datetime
from typing import Any

import pandas as pd

from bic.generator.anomalies import DeclarationBrute
from bic.generator.profiles import TAUX_ANOMALIE_PAR_PROFIL, ProfilDeclarant
from bic.identity.evaluation import MetriquesIdentite, distribution_taille_clusters
from bic.reporting.solvabilite import bande_de_risque, calculer_cutoffs_bandes
from bic.scoring.evaluate import ResultatEvaluation
from bic.scoring.features import LIBELLES_FEATURES
from bic.scoring.scorecard import (
    ODDS_REFERENCE,
    PDO,
    SCORE_MAX,
    SCORE_MIN,
    SCORE_REFERENCE,
    Scorecard,
)
from bic.validation.engine import RapportValidation
from bic.validation.evaluation import MetriquesValidation
from bic.validation.rules import catalogue_regles

#: Champs suivis pour le calcul de la complétude, avec leur libellé lisible.
_CHAMPS_COMPLETUDE_EMPRUNTEUR: dict[str, str] = {
    "identite_principale": "Nom / raison sociale",
    "piece_identification": "Pièce d'identité ou NIF",
    "telephone": "Téléphone",
}
_CHAMPS_COMPLETUDE_CONTRAT: dict[str, str] = {
    "date_octroi": "Date d'octroi",
    "date_echeance": "Date d'échéance",
    "montant_octroye": "Montant octroyé",
    "encours": "Encours",
    "classification": "Classification",
}

_ORDRE_PROFILS = ("excellent", "moyen", "defaillant")
_ORDRE_SEVERITES = ("BLOQUANT", "MAJEUR", "MINEUR")
_BANDES = ("A", "B", "C", "D", "E")
#: Nombre maximum de points conservés pour tracer la courbe ROC.
_POINTS_ROC = 60
#: Nombre de classes de l'histogramme de scores.
_CLASSES_HISTOGRAMME = 24


def _valeur_effective_emprunteur(champ: str, champs: dict[str, str]) -> str:
    if champ == "identite_principale":
        return champs["nom"] if champs["type_personne"] == "PP" else champs["raison_sociale"]
    if champ == "piece_identification":
        return champs["numero_piece"] if champs["type_personne"] == "PP" else champs["nif"]
    return champs.get(champ, "")


def _calculer_completude(declarations: list[DeclarationBrute]) -> list[dict[str, Any]]:
    """Taux de complétude (part des valeurs non vides) des champs clés."""
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

    libelles = {**_CHAMPS_COMPLETUDE_EMPRUNTEUR, **_CHAMPS_COMPLETUDE_CONTRAT}
    return [
        {
            "champ": champ,
            "libelle": libelles[champ],
            "taux_completude": (rempli / total if total else 1.0),
            "nb_manquants": total - rempli,
        }
        for champ, (rempli, total) in compteurs.items()
    ]


def _classement_declarants(
    rapports: list[RapportValidation], profils_par_code: dict[str, ProfilDeclarant]
) -> list[dict[str, Any]]:
    """Classe les déclarants par taux de rejet décroissant, agrégé sur tous leurs arrêtés."""
    totaux: dict[str, list[int]] = {}
    for rapport in rapports:
        rejetes, reserve, total = totaux.setdefault(rapport.code_declarant, [0, 0, 0])
        totaux[rapport.code_declarant] = [
            rejetes + rapport.nombre_contrats_rejetes,
            reserve + rapport.nombre_contrats_reserve,
            total + rapport.nombre_contrats,
        ]

    classement = []
    for code, (rejetes, reserve, total) in totaux.items():
        profil = profils_par_code.get(code)
        classement.append(
            {
                "code_declarant": code,
                "raison_sociale": profil.raison_sociale if profil else code,
                "type_etablissement": profil.type_etablissement if profil else "inconnu",
                "profil_qualite": profil.qualite if profil else "inconnu",
                "taux_rejet": (rejetes / total if total else 0.0),
                "taux_reserve": (reserve / total if total else 0.0),
                "nb_contrats": total,
                "nb_rejetes": rejetes,
            }
        )
    return sorted(classement, key=lambda d: d["taux_rejet"], reverse=True)


def _top_erreurs(rapports: list[RapportValidation], n: int = 10) -> list[dict[str, Any]]:
    """Codes d'erreur les plus fréquents, enrichis de leur libellé et de leur sévérité."""
    catalogue = {r["code"]: r for r in catalogue_regles()}
    compteur: dict[str, int] = {}
    for rapport in rapports:
        for rejet in rapport.rejets:
            compteur[rejet.code] = compteur.get(rejet.code, 0) + 1

    top = sorted(compteur.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [
        {
            "code": code,
            "libelle_fr": catalogue.get(code, {}).get("libelle_fr", "Erreur de structure XML"),
            "severite": catalogue.get(code, {}).get("severite", "BLOQUANT"),
            "occurrences": occurrences,
        }
        for code, occurrences in top
    ]


def _repartition_severite(rapports: list[RapportValidation]) -> list[dict[str, Any]]:
    """Répartition des rejets par niveau de gravité."""
    compteur: dict[str, int] = {}
    for rapport in rapports:
        for rejet in rapport.rejets:
            compteur[rejet.severite] = compteur.get(rejet.severite, 0) + 1
    total = sum(compteur.values())
    return [
        {
            "severite": severite,
            "occurrences": compteur.get(severite, 0),
            "part": (compteur.get(severite, 0) / total if total else 0.0),
        }
        for severite in _ORDRE_SEVERITES
    ]


def _evolution_mensuelle(
    rapports: list[RapportValidation], profils_par_code: dict[str, ProfilDeclarant]
) -> dict[str, Any]:
    """Taux de rejet mensuel, une série par profil de qualité déclarative."""
    arretes = sorted({rapport.date_arrete for rapport in rapports})

    totaux: dict[tuple[str, datetime.date], list[int]] = {}
    for rapport in rapports:
        profil = profils_par_code[rapport.code_declarant].qualite
        cle = (profil, rapport.date_arrete)
        rejetes, total = totaux.setdefault(cle, [0, 0])
        totaux[cle] = [rejetes + rapport.nombre_contrats_rejetes, total + rapport.nombre_contrats]

    series = []
    for profil in _ORDRE_PROFILS:
        taux = []
        for arrete in arretes:
            rejetes, total = totaux.get((profil, arrete), [0, 0])
            taux.append(rejetes / total if total else 0.0)
        series.append(
            {
                "profil": profil,
                "taux_anomalie_cible": TAUX_ANOMALIE_PAR_PROFIL[profil],
                "taux_rejet": taux,
            }
        )

    return {"arretes": [a.isoformat() for a in arretes], "series": series}


def _echantillonner(points: list[float], n: int) -> list[float]:
    """Réduit une liste à au plus `n` points, en conservant les extrémités."""
    if len(points) <= n:
        return points
    pas = (len(points) - 1) / (n - 1)
    return [points[round(i * pas)] for i in range(n)]


def _courbe_roc(resultat: ResultatEvaluation) -> list[dict[str, float]]:
    """Courbe ROC échantillonnée, prête à tracer."""
    fpr = _echantillonner(resultat.taux_fpr, _POINTS_ROC)
    tpr = _echantillonner(resultat.taux_tpr, _POINTS_ROC)
    return [{"fpr": f, "tpr": t} for f, t in zip(fpr, tpr, strict=True)]


def _table_gains(resultat: ResultatEvaluation) -> list[dict[str, Any]]:
    """Table de gains par décile de score, du plus risqué au moins risqué."""
    return [
        {
            "decile": int(decile),
            "nb_emprunteurs": int(ligne["nb_emprunteurs"]),
            "nb_defauts": int(ligne["nb_defauts"]),
            "taux_defaut": float(ligne["taux_defaut"]),
        }
        for decile, ligne in resultat.table_gains.iterrows()
    ]


def _histogramme_scores(scores: pd.Series) -> list[dict[str, Any]]:
    """Distribution des scores en classes régulières."""
    minimum, maximum = int(scores.min()), int(scores.max())
    if minimum == maximum:
        return [{"borne_inf": minimum, "borne_sup": maximum, "nb_emprunteurs": int(len(scores))}]

    comptes, bornes = pd.cut(scores, bins=_CLASSES_HISTOGRAMME, retbins=True)
    effectifs = comptes.value_counts().sort_index()
    return [
        {
            "borne_inf": round(float(bornes[i]), 1),
            "borne_sup": round(float(bornes[i + 1]), 1),
            "nb_emprunteurs": int(effectif),
        }
        for i, effectif in enumerate(effectifs)
    ]


def _bandes_risque(
    features: pd.DataFrame, scores: pd.Series, bornes: tuple[float, float, float, float]
) -> list[dict[str, Any]]:
    """Effectif et taux de défaut observé par bande de risque A (meilleure) à E (pire)."""
    table = pd.DataFrame(
        {
            "bande": scores.map(lambda s: bande_de_risque(s, bornes)),
            "defaut": features["defaut"].to_numpy(),
            "score": scores.to_numpy(),
        }
    )
    agrege = table.groupby("bande").agg(
        nb=("defaut", "count"), taux_defaut=("defaut", "mean"), score_min=("score", "min")
    )
    agrege = agrege.reindex(_BANDES)

    return [
        {
            "bande": bande,
            "nb_emprunteurs": int(ligne["nb"]) if pd.notna(ligne["nb"]) else 0,
            "taux_defaut_observe": float(ligne["taux_defaut"])
            if pd.notna(ligne["taux_defaut"])
            else 0.0,
            "score_plancher": int(ligne["score_min"]) if pd.notna(ligne["score_min"]) else 0,
        }
        for bande, ligne in agrege.iterrows()
    ]


def _variables_scorecard(scorecard: Scorecard) -> list[dict[str, Any]]:
    """Variables retenues par le modèle, avec leur pouvoir prédictif (IV) et leur poids."""
    return sorted(
        (
            {
                "nom": variable.nom,
                "libelle": LIBELLES_FEATURES.get(variable.nom, variable.nom),
                "iv": variable.iv,
                "coefficient": variable.coefficient,
                "nb_classes": len(variable.bins),
            }
            for variable in scorecard.variables
        ),
        key=lambda v: v["iv"],
        reverse=True,
    )


def construire_donnees_dashboard(
    *,
    declarations: list[DeclarationBrute],
    rapports: list[RapportValidation],
    profiles: list[ProfilDeclarant],
    features: pd.DataFrame,
    scores: pd.Series,
    scorecard: Scorecard,
    evaluation: ResultatEvaluation,
    metriques_identite: MetriquesIdentite,
    metriques_validation: MetriquesValidation,
    mapping_bic: dict[str, str],
    volumetrie: dict[str, int],
    seed: int,
) -> dict[str, Any]:
    """Construit le dictionnaire JSON-sérialisable consommé par le tableau de bord."""
    profils_par_code = {p.code_declarant: p for p in profiles}
    bornes_bandes = calculer_cutoffs_bandes(scores)

    total_contrats = sum(r.nombre_contrats for r in rapports)
    total_acceptes = sum(r.nombre_contrats_acceptes for r in rapports)
    total_reserve = sum(r.nombre_contrats_reserve for r in rapports)
    total_rejetes = sum(r.nombre_contrats_rejetes for r in rapports)
    arretes = sorted({r.date_arrete for r in rapports})

    return {
        "meta": {
            "genere_le": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            "seed": seed,
            "nb_arretes": len(arretes),
            "periode_debut": arretes[0].isoformat() if arretes else None,
            "periode_fin": arretes[-1].isoformat() if arretes else None,
        },
        "volumetrie": volumetrie,
        "bandeau": {
            "nb_declarations_traitees": len(rapports),
            "taux_acceptation_global": (
                (total_acceptes + total_reserve) / total_contrats if total_contrats else 0.0
            ),
            "nb_emprunteurs_consolides": metriques_identite.nb_identites_predites,
            "auc_modele": evaluation.auc,
            "rappel_validation": metriques_validation.rappel_global,
            "precision_identite": metriques_identite.precision,
            "gini": evaluation.gini,
            "ks": evaluation.ks,
        },
        "decisions": [
            {"decision": "Accepté", "nb": total_acceptes},
            {"decision": "Accepté avec réserve", "nb": total_reserve},
            {"decision": "Rejeté", "nb": total_rejetes},
        ],
        "qualite": {
            "classement_declarants": _classement_declarants(rapports, profils_par_code),
            "top_erreurs": _top_erreurs(rapports),
            "repartition_severite": _repartition_severite(rapports),
            "evolution_mensuelle": _evolution_mensuelle(rapports, profils_par_code),
            "completude_par_champ": _calculer_completude(declarations),
            "catalogue_regles": catalogue_regles(),
            "detection": metriques_validation.as_dict(),
        },
        "identite": {
            **metriques_identite.as_dict(),
            "distribution_tailles": [
                {"nb_declarants": taille, "nb_identites": nb}
                for taille, nb in distribution_taille_clusters(mapping_bic).items()
            ],
        },
        "scoring": {
            "auc": evaluation.auc,
            "gini": evaluation.gini,
            "ks": evaluation.ks,
            "nb_emprunteurs_notes": int(len(features)),
            "taux_defaut_global": float(features["defaut"].mean()),
            "parametres": {
                "pdo": PDO,
                "score_reference": SCORE_REFERENCE,
                "odds_reference": ODDS_REFERENCE,
                "score_min": SCORE_MIN,
                "score_max": SCORE_MAX,
            },
            "variables": _variables_scorecard(scorecard),
            "courbe_roc": _courbe_roc(evaluation),
            "table_gains": _table_gains(evaluation),
            "histogramme_scores": _histogramme_scores(scores),
            "bandes_risque": _bandes_risque(features, scores, bornes_bandes),
        },
    }
