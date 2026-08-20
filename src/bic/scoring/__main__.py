"""CLI : ``python -m bic.scoring --train`` et ``--report <id_emprunteur_bic>``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import JeuDeDonnees, generer_jeu_de_donnees, liste_arretes
from bic.identity.cluster import EmprunteurAResoudre, resoudre_identites
from bic.reporting.solvabilite import ecrire_rapport_solvabilite
from bic.scoring.evaluate import evaluer, separer_train_test
from bic.scoring.features import COLONNES_FEATURES, construire_jeu_de_features
from bic.scoring.scorecard import Scorecard, calculer_score, entrainer_scorecard

DOSSIER_SORTIE = Path("data/generated")


def construire_pipeline(seed: int = 42) -> tuple[JeuDeDonnees, dict[str, str], pd.DataFrame]:
    """Génère les données synthétiques, résout les identités et construit le jeu de features."""
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=seed)

    entrees = [
        EmprunteurAResoudre(
            cle=f"{e.code_declarant}:{e.id_emprunteur_source}",
            type_personne=e.type_personne,
            nom=e.nom,
            prenom=e.prenom,
            raison_sociale=e.raison_sociale,
            date_naissance=e.date_naissance.isoformat() if e.date_naissance else None,
            numero_piece=e.numero_piece,
            nif=e.nif,
        )
        for e in jeu.emprunteurs
    ]
    mapping_bic = resoudre_identites(entrees)
    features = construire_jeu_de_features(
        jeu.contrats, jeu.situations, mapping_bic, liste_arretes()
    )
    return jeu, mapping_bic, features


def _entrainer(seed: int) -> None:
    _jeu, _mapping, features = construire_pipeline(seed)
    train, test = separer_train_test(features)

    scorecard = entrainer_scorecard(train, COLONNES_FEATURES)
    scores_test = test.apply(
        lambda ligne: calculer_score(scorecard, ligne[COLONNES_FEATURES].to_dict())[0], axis=1
    )

    resultat = evaluer(scores_test, test["defaut"])
    print(f"AUC : {resultat.auc:.3f}  Gini : {resultat.gini:.3f}  KS : {resultat.ks:.3f}")
    print(resultat.table_gains)

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    (DOSSIER_SORTIE / "scoring_metrics.json").write_text(
        json.dumps({"auc": resultat.auc, "gini": resultat.gini, "ks": resultat.ks}, indent=2),
        encoding="utf-8",
    )


def _construire_rapport(
    id_emprunteur_bic: str,
    scorecard: Scorecard,
    jeu: JeuDeDonnees,
    mapping_bic: dict[str, str],
    observation: dict,
) -> Path:
    score, contributions = calculer_score(scorecard, observation)

    contrats_du_client = [
        c
        for c in jeu.contrats
        if mapping_bic.get(f"{c.code_declarant}:{c.id_emprunteur_source}") == id_emprunteur_bic
    ]
    ids_contrats = {(c.code_declarant, c.id_contrat_source) for c in contrats_du_client}
    situations_du_client = sorted(
        (s for s in jeu.situations if (s.code_declarant, s.id_contrat_source) in ids_contrats),
        key=lambda s: s.date_arrete,
    )

    derniere_date = max(s.date_arrete for s in situations_du_client)
    engagements = [
        {
            "code_declarant": c.code_declarant,
            "type_credit": c.type_credit,
            "encours": f"{s.encours:.2f}",
            "classification": s.classification,
        }
        for c in contrats_du_client
        for s in situations_du_client
        if (s.code_declarant, s.id_contrat_source) == (c.code_declarant, c.id_contrat_source)
        and s.date_arrete == derniere_date
    ]
    jours_retard_max_par_arrete: dict = {}
    for s in situations_du_client:
        jours_retard_max_par_arrete[s.date_arrete] = max(
            jours_retard_max_par_arrete.get(s.date_arrete, 0), s.jours_retard
        )
    historique = [
        {"date_arrete": date_arrete.isoformat(), "jours_retard": jours_retard}
        for date_arrete, jours_retard in sorted(jours_retard_max_par_arrete.items())[-12:]
    ]

    chemin = DOSSIER_SORTIE / "rapports_solvabilite" / f"{id_emprunteur_bic}.html"
    ecrire_rapport_solvabilite(
        chemin, id_emprunteur_bic, score, contributions, engagements, historique
    )
    return chemin


def _rapport(id_emprunteur_bic: str, seed: int) -> None:
    jeu, mapping_bic, features = construire_pipeline(seed)
    scorecard = entrainer_scorecard(features, COLONNES_FEATURES)

    ligne = features[features["id_emprunteur_bic"] == id_emprunteur_bic]
    if ligne.empty:
        raise SystemExit(f"Emprunteur {id_emprunteur_bic!r} introuvable dans le jeu de données.")

    observation = ligne.iloc[0][COLONNES_FEATURES].to_dict()
    chemin = _construire_rapport(id_emprunteur_bic, scorecard, jeu, mapping_bic, observation)
    print(f"Rapport de solvabilité écrit dans {chemin}")


def main() -> None:
    """Point d'entrée CLI du module de scoring."""
    parser = argparse.ArgumentParser(description="Scoring de solvabilité BIC.")
    parser.add_argument(
        "--train", action="store_true", help="Entraîne la scorecard et affiche les métriques."
    )
    parser.add_argument(
        "--report", metavar="ID_EMPRUNTEUR_BIC", help="Génère le rapport HTML d'un emprunteur."
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.train:
        _entrainer(args.seed)
    elif args.report:
        _rapport(args.report, args.seed)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
