"""Tests unitaires du scoring de solvabilité (phase 5)."""

from __future__ import annotations

from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import generer_jeu_de_donnees, liste_arretes
from bic.identity.cluster import EmprunteurAResoudre, resoudre_identites
from bic.reporting.solvabilite import bande_de_risque
from bic.scoring.evaluate import evaluer, separer_train_test
from bic.scoring.features import COLONNES_FEATURES, construire_jeu_de_features
from bic.scoring.scorecard import calculer_score, entrainer_scorecard


def _jeu_de_features():
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=1500, n_contrats=2500)

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


def test_construire_jeu_de_features_a_les_bonnes_colonnes() -> None:
    _jeu, _mapping, features = _jeu_de_features()
    assert not features.empty
    for colonne in [*COLONNES_FEATURES, "defaut", "id_emprunteur_bic"]:
        assert colonne in features.columns
    assert set(features["defaut"].unique()) <= {0, 1}


def test_features_toujours_positives_ou_nulles() -> None:
    _jeu, _mapping, features = _jeu_de_features()
    for colonne in ("encours_total", "nb_declarants", "nb_contrats_actifs", "anciennete_jours"):
        assert (features[colonne] >= 0).all()


def test_entrainer_scorecard_et_calculer_score_dans_la_plage() -> None:
    _jeu, _mapping, features = _jeu_de_features()
    scorecard = entrainer_scorecard(features, COLONNES_FEATURES)
    assert len(scorecard.variables) > 0

    for _, ligne in features.head(20).iterrows():
        score, contributions = calculer_score(scorecard, ligne[COLONNES_FEATURES].to_dict())
        assert 300 <= score <= 850
        assert len(contributions) == len(scorecard.variables)


def test_evaluer_produit_auc_gini_ks_coherents() -> None:
    _jeu, _mapping, features = _jeu_de_features()
    train, test = separer_train_test(features)
    scorecard = entrainer_scorecard(train, COLONNES_FEATURES)

    scores_test = test.apply(
        lambda ligne: calculer_score(scorecard, ligne[COLONNES_FEATURES].to_dict())[0], axis=1
    )
    resultat = evaluer(scores_test, test["defaut"])

    assert 0.0 <= resultat.auc <= 1.0
    assert resultat.gini == 2 * resultat.auc - 1
    assert 0.0 <= resultat.ks <= 1.0
    assert not resultat.table_gains.empty


def test_bande_de_risque_bornes() -> None:
    assert bande_de_risque(800) == "A"
    assert bande_de_risque(720) == "B"
    assert bande_de_risque(670) == "C"
    assert bande_de_risque(610) == "D"
    assert bande_de_risque(400) == "E"
