"""Agrégation des variables prédictives (features) par identité consolidée.

Fenêtre d'observation : les 6 premiers arrêtés (features). Fenêtre de
performance : les 6 arrêtés suivants (cible). Aucune variable construite sur
la fenêtre de performance n'entre dans le calcul des features, pour éviter
toute fuite de cible.
"""

from __future__ import annotations

import datetime

import pandas as pd

from bic.generator.synthetic import ContratRecord, SituationRecord

#: Colonnes de features produites par `construire_jeu_de_features`.
COLONNES_FEATURES: list[str] = [
    "nb_declarants",
    "nb_contrats_actifs",
    "encours_total",
    "ratio_impaye_encours",
    "max_jours_retard",
    "nb_mois_douteux_ou_pire",
    "anciennete_jours",
    "taux_couverture_garantie",
    "nb_types_credit",
]


def construire_jeu_de_features(
    contrats: list[ContratRecord],
    situations: list[SituationRecord],
    mapping_bic: dict[str, str],
    arretes: list[datetime.date],
) -> pd.DataFrame:
    """Construit un DataFrame (une ligne par `id_emprunteur_bic`) de features et de cible.

    La cible `defaut` vaut 1 si au moins un contrat de l'emprunteur atteint
    plus de 90 jours de retard durant la fenêtre de performance.
    """
    if len(arretes) < 12:
        raise ValueError(
            "Il faut au moins 12 arrêtés pour définir les fenêtres d'observation et de performance."
        )

    arretes_tries = sorted(arretes)
    fenetre_observation = set(arretes_tries[:6])
    fenetre_performance = set(arretes_tries[6:12])
    date_cutoff = arretes_tries[5]

    contrats_par_cle = {(c.code_declarant, c.id_contrat_source): c for c in contrats}

    def _id_bic(contrat: ContratRecord) -> str | None:
        return mapping_bic.get(f"{contrat.code_declarant}:{contrat.id_emprunteur_source}")

    situations_obs: dict[str, list[tuple[ContratRecord, SituationRecord]]] = {}
    situations_perf: dict[str, list[tuple[ContratRecord, SituationRecord]]] = {}

    for situation in situations:
        contrat = contrats_par_cle.get((situation.code_declarant, situation.id_contrat_source))
        if contrat is None:
            continue
        bic = _id_bic(contrat)
        if bic is None:
            continue
        if situation.date_arrete in fenetre_observation:
            situations_obs.setdefault(bic, []).append((contrat, situation))
        elif situation.date_arrete in fenetre_performance:
            situations_perf.setdefault(bic, []).append((contrat, situation))

    lignes = []
    for bic, paires in situations_obs.items():
        derniere_date_obs = max(s.date_arrete for _, s in paires)
        situations_derniere_date = [(c, s) for c, s in paires if s.date_arrete == derniere_date_obs]

        contrats_uniques = {(c.code_declarant, c.id_contrat_source): c for c, _ in paires}
        encours_total = sum(float(s.encours) for _, s in situations_derniere_date)
        impaye_total = sum(float(s.montant_impaye) for _, s in situations_derniere_date)
        montant_octroye_total = sum(c.montant_octroye for c in contrats_uniques.values())
        montant_garantie_total = sum(c.montant_garantie for c in contrats_uniques.values())
        plus_ancien = min(c.date_octroi for c in contrats_uniques.values())

        cible = 1 if any(s.jours_retard > 90 for _, s in situations_perf.get(bic, [])) else 0

        lignes.append(
            {
                "id_emprunteur_bic": bic,
                "nb_declarants": len({c.code_declarant for c in contrats_uniques.values()}),
                "nb_contrats_actifs": len(contrats_uniques),
                "encours_total": encours_total,
                "ratio_impaye_encours": (impaye_total / encours_total) if encours_total else 0.0,
                "max_jours_retard": max(s.jours_retard for _, s in paires),
                "nb_mois_douteux_ou_pire": sum(
                    1 for _, s in paires if s.classification in ("douteux", "contentieux")
                ),
                "anciennete_jours": (date_cutoff - plus_ancien).days,
                "taux_couverture_garantie": min(
                    (montant_garantie_total / montant_octroye_total)
                    if montant_octroye_total
                    else 0.0,
                    1.0,
                ),
                "nb_types_credit": len({c.type_credit for c in contrats_uniques.values()}),
                "defaut": cible,
            }
        )

    return pd.DataFrame(lignes)
