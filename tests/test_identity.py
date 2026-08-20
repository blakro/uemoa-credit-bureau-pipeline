"""Tests unitaires de la résolution d'identité (phase 4)."""

from __future__ import annotations

import json
from pathlib import Path

from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import generer_jeu_de_donnees
from bic.identity.blocking import cle_phonetique_simplifiee, cles_de_blocage
from bic.identity.cluster import EmprunteurAResoudre, resoudre_identites
from bic.identity.evaluation import distribution_taille_clusters, evaluer_appariement
from bic.identity.match import comparer
from bic.identity.normalize import normaliser_identifiant, normaliser_nom, normaliser_nom_complet

SEUIL_PRECISION_MINIMALE = 0.95

DOSSIER_SORTIE = Path("data/generated")


# ============================= normalize =============================


def test_normaliser_nom_retire_accents_et_particules() -> None:
    assert normaliser_nom("Aïchatou de la Cissé") == "AICHATOU CISSE"


def test_normaliser_nom_complet_concatene() -> None:
    assert normaliser_nom_complet("Issoufou", "Amadou") == "ISSOUFOU AMADOU"


def test_normaliser_identifiant_retire_espaces_et_tirets() -> None:
    assert normaliser_identifiant("ne-cni-12345678") == "NECNI12345678"


# ============================= blocking =============================


def test_cle_phonetique_regroupe_variantes_proches() -> None:
    assert cle_phonetique_simplifiee("BOUBACAR") == cle_phonetique_simplifiee("BOUBAKAR")


def test_cles_de_blocage_inclut_la_cle_piece() -> None:
    cles = cles_de_blocage("NECNI12345678", "ISSOUFOU AMADOU", "1985-04-12")
    assert "PIECE:NECNI12345678" in cles


# ============================= match =============================


def test_comparer_numero_piece_identique_est_certaine() -> None:
    resultat = comparer(
        "NECNI123", "ISSOUFOU AMADOU", "1985-04-12", "NECNI123", "AUTRE NOM", "1990-01-01"
    )
    assert resultat.decision == "certaine"


def test_comparer_noms_tres_differents_sans_lien() -> None:
    resultat = comparer("", "ISSOUFOU AMADOU", "1985-04-12", "", "TRAORE FATIMATA", "1970-06-01")
    assert resultat.decision == "aucune"


def test_comparer_meme_nom_et_naissance_est_probable() -> None:
    resultat = comparer("", "ISSOUFOU AMADOU", "1985-04-12", "", "ISSOUFOU AMADOU", "1985-04-12")
    assert resultat.decision == "probable"


# ============================= cluster =============================


def test_resoudre_identites_fusionne_par_numero_piece() -> None:
    entrees = [
        EmprunteurAResoudre(
            "A", "PP", "Issoufou", "Amadou", None, "1985-04-12", "NE-CNI-12345678", None
        ),
        EmprunteurAResoudre(
            "B", "PP", "ISSOUFOU", "A.", None, "1985-04-12", "NE-CNI-12345678", None
        ),
        EmprunteurAResoudre(
            "C", "PP", "Traore", "Fatimata", None, "1970-06-01", "NE-CNI-99999999", None
        ),
    ]
    resultat = resoudre_identites(entrees)
    assert resultat["A"] == resultat["B"]
    assert resultat["C"] != resultat["A"]


def test_resoudre_identites_est_stable_quel_que_soit_l_ordre_d_entree() -> None:
    """L'id_emprunteur_bic attribué à un cluster ne doit pas dépendre de l'ordre des entrées."""
    entrees = [
        EmprunteurAResoudre(
            "A", "PP", "Issoufou", "Amadou", None, "1985-04-12", "NE-CNI-12345678", None
        ),
        EmprunteurAResoudre(
            "B", "PP", "ISSOUFOU", "A.", None, "1985-04-12", "NE-CNI-12345678", None
        ),
        EmprunteurAResoudre(
            "C", "PP", "Traore", "Fatimata", None, "1970-06-01", "NE-CNI-99999999", None
        ),
    ]
    resultat_ordre_original = resoudre_identites(entrees)
    resultat_ordre_inverse = resoudre_identites(list(reversed(entrees)))
    assert resultat_ordre_original == resultat_ordre_inverse


# ============================= évaluation décisive =============================


def test_precision_rappel_f1_sur_verite_terrain() -> None:
    """Mesure précision/rappel/F1 de l'appariement contre la vérité-terrain du générateur.

    La précision est l'exigence prioritaire (≥ 0,95) : sur-fusionner deux
    personnes distinctes est une faute grave dans un BIC, bien plus grave
    que manquer un doublon.
    """
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=2000, n_contrats=100)

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
    verite_par_cle = {
        f"{e.code_declarant}:{e.id_emprunteur_source}": e.identite_verite for e in jeu.emprunteurs
    }

    predictions = resoudre_identites(entrees)
    metriques = evaluer_appariement(predictions, verite_par_cle)

    print(
        f"\nPrécision : {metriques.precision:.3f}  "
        f"Rappel : {metriques.rappel:.3f}  F1 : {metriques.f1:.3f}"
    )
    print(
        f"VP={metriques.vrais_positifs} FP={metriques.faux_positifs} FN={metriques.faux_negatifs}"
    )

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    (DOSSIER_SORTIE / "identity_metrics.json").write_text(
        json.dumps(metriques.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    assert metriques.precision >= SEUIL_PRECISION_MINIMALE, (
        f"Précision {metriques.precision:.1%} < seuil {SEUIL_PRECISION_MINIMALE:.0%}"
    )


def test_distribution_taille_clusters_totalise_les_enregistrements() -> None:
    """La distribution des tailles de clusters doit couvrir tous les enregistrements."""
    entrees = [
        EmprunteurAResoudre(
            "A", "PP", "Issoufou", "Amadou", None, "1985-04-12", "NE-CNI-12345678", None
        ),
        EmprunteurAResoudre(
            "B", "PP", "ISSOUFOU", "A.", None, "1985-04-12", "NE-CNI-12345678", None
        ),
        EmprunteurAResoudre(
            "C", "PP", "Traore", "Fatimata", None, "1970-06-01", "NE-CNI-99999999", None
        ),
    ]
    distribution = distribution_taille_clusters(resoudre_identites(entrees))

    assert sum(taille * nb for taille, nb in distribution.items()) == len(entrees)
    assert distribution == {1: 1, 2: 1}
