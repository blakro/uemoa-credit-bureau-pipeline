"""Tests unitaires du générateur de données synthétiques (phase 2)."""

from __future__ import annotations

from bic.generator.anomalies import assembler_declarations, injecter_anomalies
from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import generer_jeu_de_donnees


def test_determinisme_du_seed() -> None:
    """Deux générations avec la même graine doivent produire des données identiques."""
    profiles = get_declarant_profiles()
    jeu_1 = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=300, n_contrats=500)
    jeu_2 = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=300, n_contrats=500)

    assert [e.__dict__ for e in jeu_1.emprunteurs] == [e.__dict__ for e in jeu_2.emprunteurs]
    assert [c.__dict__ for c in jeu_1.contrats] == [c.__dict__ for c in jeu_2.contrats]
    assert [s.__dict__ for s in jeu_1.situations] == [s.__dict__ for s in jeu_2.situations]


def test_seeds_differentes_donnent_des_jeux_differents() -> None:
    """Deux graines différentes doivent produire des jeux de données différents."""
    profiles = get_declarant_profiles()
    jeu_1 = generer_jeu_de_donnees(profiles=profiles, seed=1, n_emprunteurs=300, n_contrats=500)
    jeu_2 = generer_jeu_de_donnees(profiles=profiles, seed=2, n_emprunteurs=300, n_contrats=500)

    assert [e.__dict__ for e in jeu_1.emprunteurs] != [e.__dict__ for e in jeu_2.emprunteurs]


def test_classification_coherente_avec_jours_retard_sur_donnees_propres() -> None:
    """Sur des données non corrompues, la classification doit toujours suivre la grille standard."""
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=300, n_contrats=500)

    for situation in jeu.situations:
        if situation.jours_retard == 0:
            assert situation.classification == "sain"
        elif situation.jours_retard <= 30:
            assert situation.classification == "sensible"
        elif situation.jours_retard <= 90:
            assert situation.classification == "douteux"
        else:
            assert situation.classification == "contentieux"


def test_environ_15_pourcent_des_identites_sont_dupliquees() -> None:
    """La vérité-terrain doit contenir des clusters de taille 2 à 4 pour ~15 % des identités."""
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=2000, n_contrats=100)

    tailles_par_cluster: dict[int, int] = {}
    for emprunteur in jeu.emprunteurs:
        tailles_par_cluster[emprunteur.identite_verite] = (
            tailles_par_cluster.get(emprunteur.identite_verite, 0) + 1
        )

    clusters_dupliques = [taille for taille in tailles_par_cluster.values() if taille > 1]
    fraction_dupliquee = sum(clusters_dupliques) / len(jeu.emprunteurs)

    assert 0.08 <= fraction_dupliquee <= 0.35
    assert all(2 <= taille <= 4 for taille in clusters_dupliques)


def test_taux_anomalie_par_profil_respecte() -> None:
    """Le taux d'anomalies observé par déclarant doit être proche du taux cible de son profil."""
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=1500, n_contrats=2500)
    declarations = assembler_declarations(jeu)
    declarations, journal = injecter_anomalies(declarations, profiles, seed=42)

    total_enregistrements: dict[str, int] = {}
    for declaration in declarations:
        total_enregistrements[declaration.code_declarant] = (
            total_enregistrements.get(declaration.code_declarant, 0)
            + len(declaration.emprunteurs)
            + len(declaration.contrats)
        )

    total_anomalies: dict[str, int] = {}
    for anomalie in journal:
        total_anomalies[anomalie.code_declarant] = (
            total_anomalies.get(anomalie.code_declarant, 0) + 1
        )

    profil_par_code = {p.code_declarant: p for p in profiles}
    for code_declarant, total in total_enregistrements.items():
        taux_observe = total_anomalies.get(code_declarant, 0) / total
        taux_attendu = profil_par_code[code_declarant].taux_anomalie
        assert abs(taux_observe - taux_attendu) < 0.05, (code_declarant, taux_observe, taux_attendu)
