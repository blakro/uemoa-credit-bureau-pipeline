"""Tests d'agrégation du tableau de bord (phase 6).

Le tableau de bord est le livrable visible du projet : ces tests vérifient que
son payload est complet, cohérent, et entièrement sérialisable en JSON.
"""

from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from bic.generator.anomalies import assembler_declarations, injecter_anomalies
from bic.generator.export_xml import construire_arbre_xml
from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import DERNIER_ARRETE, generer_jeu_de_donnees, liste_arretes
from bic.identity.cluster import EmprunteurAResoudre, resoudre_identites
from bic.identity.evaluation import evaluer_appariement
from bic.reporting.dashboard import construire_donnees_dashboard
from bic.scoring.evaluate import evaluer
from bic.scoring.features import COLONNES_FEATURES, construire_jeu_de_features
from bic.scoring.scorecard import calculer_score, entrainer_scorecard
from bic.validation.engine import valider_fichier
from bic.validation.evaluation import evaluer_detection


@pytest.fixture(scope="module")
def donnees_dashboard() -> dict:
    """Exécute un pipeline réduit de bout en bout et retourne le payload du tableau de bord."""
    seed = 42
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=seed, n_emprunteurs=600, n_contrats=900)

    declarations = assembler_declarations(jeu)
    declarations, journal = injecter_anomalies(declarations, profiles, seed=seed)
    declarants_connus = {p.code_declarant for p in profiles}

    rapports = []
    for declaration in declarations:
        arbre = construire_arbre_xml(declaration)
        buf = io.BytesIO()
        arbre.write(buf, encoding="utf-8", xml_declaration=True)
        rapports.append(
            valider_fichier(
                buf.getvalue(),
                declarants_connus,
                date_reference=DERNIER_ARRETE,
                code_declarant_attendu=declaration.code_declarant,
            )
        )

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
    verite = {
        f"{e.code_declarant}:{e.id_emprunteur_source}": e.identite_verite for e in jeu.emprunteurs
    }

    features = construire_jeu_de_features(
        jeu.contrats, jeu.situations, mapping_bic, liste_arretes()
    )
    scorecard = entrainer_scorecard(features, COLONNES_FEATURES)
    scores = features.apply(
        lambda ligne: calculer_score(scorecard, ligne[COLONNES_FEATURES].to_dict())[0], axis=1
    )

    return construire_donnees_dashboard(
        declarations=declarations,
        rapports=rapports,
        profiles=profiles,
        features=features,
        scores=scores,
        scorecard=scorecard,
        evaluation=evaluer(scores, features["defaut"]),
        metriques_identite=evaluer_appariement(mapping_bic, verite),
        metriques_validation=evaluer_detection(journal, rapports),
        mapping_bic=mapping_bic,
        volumetrie={
            "nb_declarants": len(profiles),
            "nb_emprunteurs_declares": len(jeu.emprunteurs),
            "nb_contrats": len(jeu.contrats),
            "nb_situations": len(jeu.situations),
            "nb_fichiers_declaration": len(declarations),
            "nb_anomalies_injectees": len(journal),
        },
        seed=seed,
    )


def test_toutes_les_sections_sont_presentes(donnees_dashboard: dict) -> None:
    """Le payload doit exposer les six sections attendues par la page."""
    for cle in ("meta", "volumetrie", "bandeau", "decisions", "qualite", "identite", "scoring"):
        assert cle in donnees_dashboard


def test_payload_est_serialisable_en_json(donnees_dashboard: dict) -> None:
    """Aucun type NumPy/pandas ne doit fuiter : le payload doit passer json.dumps tel quel."""
    recharge = json.loads(json.dumps(donnees_dashboard, ensure_ascii=False))
    assert recharge["bandeau"]["nb_declarations_traitees"] > 0


def test_bandeau_expose_des_taux_coherents(donnees_dashboard: dict) -> None:
    bandeau = donnees_dashboard["bandeau"]
    for cle in ("taux_acceptation_global", "rappel_validation", "precision_identite", "auc_modele"):
        assert 0.0 <= bandeau[cle] <= 1.0
    assert bandeau["nb_emprunteurs_consolides"] > 0


def test_decisions_totalisent_les_contrats_controles(donnees_dashboard: dict) -> None:
    """Accepté + réserve + rejeté doit couvrir exactement les contrats soumis au contrôle."""
    total_decisions = sum(d["nb"] for d in donnees_dashboard["decisions"])
    assert total_decisions > 0
    assert len(donnees_dashboard["decisions"]) == 3


def test_qualite_documente_les_quinze_regles(donnees_dashboard: dict) -> None:
    catalogue = donnees_dashboard["qualite"]["catalogue_regles"]
    assert [e["code"] for e in catalogue] == [f"E{n:03d}" for n in range(1, 16)]


def test_classement_declarants_trie_par_taux_de_rejet(donnees_dashboard: dict) -> None:
    taux = [d["taux_rejet"] for d in donnees_dashboard["qualite"]["classement_declarants"]]
    assert taux == sorted(taux, reverse=True)


def test_evolution_mensuelle_couvre_douze_arretes(donnees_dashboard: dict) -> None:
    evolution = donnees_dashboard["qualite"]["evolution_mensuelle"]
    assert len(evolution["arretes"]) == 12
    assert len(evolution["series"]) == 3
    for serie in evolution["series"]:
        assert len(serie["taux_rejet"]) == 12


def test_identite_distribution_totalise_les_enregistrements(donnees_dashboard: dict) -> None:
    identite = donnees_dashboard["identite"]
    total = sum(d["nb_declarants"] * d["nb_identites"] for d in identite["distribution_tailles"])
    assert total == identite["nb_enregistrements"]


def test_scoring_expose_courbe_roc_et_gains(donnees_dashboard: dict) -> None:
    scoring = donnees_dashboard["scoring"]

    assert len(scoring["courbe_roc"]) >= 2
    for point in scoring["courbe_roc"]:
        assert 0.0 <= point["fpr"] <= 1.0
        assert 0.0 <= point["tpr"] <= 1.0

    assert scoring["table_gains"]
    assert scoring["variables"]
    ivs = [v["iv"] for v in scoring["variables"]]
    assert ivs == sorted(ivs, reverse=True)


def test_scoring_bandes_couvrent_tous_les_emprunteurs_notes(donnees_dashboard: dict) -> None:
    scoring = donnees_dashboard["scoring"]
    total_bandes = sum(b["nb_emprunteurs"] for b in scoring["bandes_risque"])
    total_histogramme = sum(c["nb_emprunteurs"] for c in scoring["histogramme_scores"])

    assert total_bandes == scoring["nb_emprunteurs_notes"]
    assert total_histogramme == scoring["nb_emprunteurs_notes"]
    assert [b["bande"] for b in scoring["bandes_risque"]] == ["A", "B", "C", "D", "E"]


def test_completude_bornee_entre_zero_et_un(donnees_dashboard: dict) -> None:
    for champ in donnees_dashboard["qualite"]["completude_par_champ"]:
        assert 0.0 <= champ["taux_completude"] <= 1.0
        assert champ["libelle"]


def test_histogramme_scores_a_des_classes_ordonnees(donnees_dashboard: dict) -> None:
    classes = donnees_dashboard["scoring"]["histogramme_scores"]
    bornes = [c["borne_inf"] for c in classes]
    assert bornes == sorted(bornes)
    assert all(c["borne_sup"] >= c["borne_inf"] for c in classes)


def test_meta_documente_la_reproductibilite(donnees_dashboard: dict) -> None:
    """La graine et la période couverte doivent figurer au payload, pour rejouer à l'identique."""
    meta = donnees_dashboard["meta"]
    assert meta["seed"] == 42
    assert meta["nb_arretes"] == 12
    assert pd.Timestamp(meta["periode_debut"]) < pd.Timestamp(meta["periode_fin"])
