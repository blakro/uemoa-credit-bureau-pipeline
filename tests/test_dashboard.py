"""Tests unitaires de l'agrégation du tableau de bord (phase 6)."""

from __future__ import annotations

import io

import pandas as pd

from bic.generator.anomalies import assembler_declarations, injecter_anomalies
from bic.generator.export_xml import construire_arbre_xml
from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import DERNIER_ARRETE, generer_jeu_de_donnees
from bic.reporting.dashboard import construire_donnees_dashboard
from bic.validation.engine import valider_fichier


def _rapports_et_declarations(seed: int = 42):
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=seed, n_emprunteurs=400, n_contrats=600)
    declarations = assembler_declarations(jeu)
    declarations, _journal = injecter_anomalies(declarations, profiles, seed=seed)
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
    return declarations, rapports, profiles


def test_construire_donnees_dashboard_a_les_bonnes_cles() -> None:
    declarations, rapports, profiles = _rapports_et_declarations()
    features = pd.DataFrame({"defaut": [0, 1, 0, 1, 0]})
    scores = pd.Series([700, 500, 650, 480, 620])

    donnees = construire_donnees_dashboard(
        declarations=declarations,
        rapports=rapports,
        profiles=profiles,
        nb_emprunteurs_consolides=350,
        features=features,
        scores=scores,
        auc=0.66,
    )

    for cle in (
        "bandeau",
        "classement_declarants",
        "top_erreurs",
        "evolution_mensuelle",
        "completude_par_champ",
        "distribution_scores",
    ):
        assert cle in donnees

    assert donnees["bandeau"]["nb_declarations_traitees"] == len(rapports)
    assert donnees["bandeau"]["nb_emprunteurs_consolides"] == 350
    assert 0.0 <= donnees["bandeau"]["taux_acceptation_global"] <= 1.0
    assert len(donnees["evolution_mensuelle"]["arretes"]) == 12
    assert len(donnees["evolution_mensuelle"]["series"]) == 3
    assert len(donnees["top_erreurs"]) <= 10
    assert sum(donnees["distribution_scores"]["nb_emprunteurs"]) == len(scores)


def test_classement_declarants_est_trie_par_taux_de_rejet_decroissant() -> None:
    declarations, rapports, profiles = _rapports_et_declarations()
    features = pd.DataFrame({"defaut": [0, 1]})
    scores = pd.Series([700, 500])

    donnees = construire_donnees_dashboard(
        declarations=declarations,
        rapports=rapports,
        profiles=profiles,
        nb_emprunteurs_consolides=10,
        features=features,
        scores=scores,
        auc=0.5,
    )

    taux = [d["taux_rejet"] for d in donnees["classement_declarants"]]
    assert taux == sorted(taux, reverse=True)
