"""Point d'entrée unique du pipeline BIC.

Enchaîne : génération -> export XML -> validation -> chargement -> résolution
d'identité -> scoring -> tableau de bord, avec des logs clairs à chaque étape.
``MYSQL_HOST`` est optionnel : sans base MySQL disponible (sandbox local),
le chargement en base est simplement sauté.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
from pathlib import Path

from bic.db import create_all_tables, create_db_engine, get_session_factory
from bic.generator.anomalies import assembler_declarations, injecter_anomalies
from bic.generator.export_xml import construire_arbre_xml, exporter_declarations
from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import generer_jeu_de_donnees, liste_arretes
from bic.identity.cluster import EmprunteurAResoudre, resoudre_identites
from bic.models import Declarant, TypeEtablissement
from bic.reporting.dashboard import construire_donnees_dashboard
from bic.reporting.rejets import ecrire_csv_rejets, ecrire_rapport_html
from bic.scoring.evaluate import evaluer, separer_train_test
from bic.scoring.features import COLONNES_FEATURES, construire_jeu_de_features
from bic.scoring.scorecard import calculer_score, entrainer_scorecard
from bic.validation.engine import valider_et_charger, valider_fichier

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bic.pipeline")

DOSSIER_DATA = Path("data/generated")
DOSSIER_DOCS_DATA = Path("docs/data")


def _analyser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rejoue l'intégralité du pipeline BIC.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _preparer_session_db(profiles: list) -> object | None:
    """Crée le schéma et les déclarants en base si MYSQL_HOST est défini, sinon None."""
    if not os.environ.get("MYSQL_HOST"):
        logger.info(
            "MYSQL_HOST absent : validation seule, sans chargement en base (normal en sandbox)."
        )
        return None

    engine = create_db_engine()
    create_all_tables(engine)
    session = get_session_factory(engine)()
    for profil in profiles:
        if session.get(Declarant, profil.code_declarant) is None:
            session.add(
                Declarant(
                    code_declarant=profil.code_declarant,
                    raison_sociale=profil.raison_sociale,
                    type_etablissement=TypeEtablissement(profil.type_etablissement),
                    pays=profil.pays,
                    date_agrement=profil.date_agrement,
                )
            )
    session.commit()
    logger.info("MYSQL_HOST détecté : les enregistrements acceptés seront chargés en base.")
    return session


def main() -> None:
    """Exécute le pipeline complet et écrit le tableau de bord dans docs/data/dashboard.json."""
    args = _analyser_arguments()

    logger.info("=== 1/6 Génération des données synthétiques (seed=%s) ===", args.seed)
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=args.seed)
    logger.info(
        "%d emprunteurs, %d contrats, %d situations générés.",
        len(jeu.emprunteurs),
        len(jeu.contrats),
        len(jeu.situations),
    )

    logger.info("=== 2/6 Assemblage des déclarations et export XML ===")
    declarations = assembler_declarations(jeu)
    declarations, journal_anomalies = injecter_anomalies(declarations, profiles, seed=args.seed)
    fichiers = exporter_declarations(declarations, DOSSIER_DATA / "declarations")
    logger.info(
        "%d fichiers de déclaration écrits, %d anomalies injectées.",
        len(fichiers),
        len(journal_anomalies),
    )

    logger.info("=== 3/6 Validation (XSD + règles métier) ===")
    declarants_connus = {p.code_declarant for p in profiles}
    session = _preparer_session_db(profiles)

    rapports = []
    dossier_rejets = DOSSIER_DATA / "rapports_rejets"
    for declaration in declarations:
        arbre = construire_arbre_xml(declaration)
        buf = io.BytesIO()
        arbre.write(buf, encoding="utf-8", xml_declaration=True)
        contenu = buf.getvalue()

        if session is not None:
            rapport = valider_et_charger(
                session,
                contenu,
                declarants_connus,
                code_declarant_attendu=declaration.code_declarant,
            )
        else:
            rapport = valider_fichier(
                contenu, declarants_connus, code_declarant_attendu=declaration.code_declarant
            )
        rapports.append(rapport)

        base = f"{declaration.code_declarant}_{declaration.date_arrete.strftime('%Y%m%d')}"
        ecrire_csv_rejets(rapport, dossier_rejets / f"{base}.csv")
        ecrire_rapport_html(rapport, dossier_rejets / f"{base}.html")

    if session is not None:
        session.close()

    total_contrats = sum(r.nombre_contrats for r in rapports)
    total_acceptes = sum(r.nombre_contrats_acceptes + r.nombre_contrats_reserve for r in rapports)
    taux_global = 100 * total_acceptes / total_contrats if total_contrats else 0.0
    logger.info(
        "%d fichiers validés, taux d'acceptation global : %.1f%%", len(rapports), taux_global
    )

    logger.info("=== 4/6 Résolution d'identité ===")
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
    nb_emprunteurs_consolides = len(set(mapping_bic.values()))
    logger.info(
        "%d emprunteurs déclarés consolidés en %d identités uniques.",
        len(entrees),
        nb_emprunteurs_consolides,
    )

    logger.info("=== 5/6 Scoring de solvabilité ===")
    features = construire_jeu_de_features(
        jeu.contrats, jeu.situations, mapping_bic, liste_arretes()
    )
    train, test = separer_train_test(features)
    scorecard = entrainer_scorecard(train, COLONNES_FEATURES)
    scores_test = test.apply(
        lambda ligne: calculer_score(scorecard, ligne[COLONNES_FEATURES].to_dict())[0], axis=1
    )
    resultat_evaluation = evaluer(scores_test, test["defaut"])
    logger.info(
        "AUC : %.3f  Gini : %.3f  KS : %.3f  (%d emprunteurs notés)",
        resultat_evaluation.auc,
        resultat_evaluation.gini,
        resultat_evaluation.ks,
        len(features),
    )

    logger.info("=== 6/6 Génération du tableau de bord ===")
    scores_tous = features.apply(
        lambda ligne: calculer_score(scorecard, ligne[COLONNES_FEATURES].to_dict())[0], axis=1
    )
    donnees_dashboard = construire_donnees_dashboard(
        declarations=declarations,
        rapports=rapports,
        profiles=profiles,
        nb_emprunteurs_consolides=nb_emprunteurs_consolides,
        features=features,
        scores=scores_tous,
        auc=resultat_evaluation.auc,
    )
    DOSSIER_DOCS_DATA.mkdir(parents=True, exist_ok=True)
    (DOSSIER_DOCS_DATA / "dashboard.json").write_text(
        json.dumps(donnees_dashboard, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Tableau de bord écrit dans %s", DOSSIER_DOCS_DATA / "dashboard.json")
    logger.info("Pipeline terminé avec succès.")


if __name__ == "__main__":
    main()
