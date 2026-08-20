"""Test décisif : rejoue la vérité-terrain d'anomalies (phase 2) et mesure le rappel du moteur."""

from __future__ import annotations

import io

from bic.generator.anomalies import assembler_declarations, injecter_anomalies
from bic.generator.export_xml import construire_arbre_xml
from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import DERNIER_ARRETE, generer_jeu_de_donnees
from bic.validation.engine import valider_fichier
from bic.validation.evaluation import evaluer_detection
from bic.validation.rules import REGLES, catalogue_regles

SEUIL_RAPPEL_MINIMAL = 0.95


def _rejouer_verite_terrain(seed: int = 42):
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=seed, n_emprunteurs=1500, n_contrats=2500)
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
    return journal, rapports


def test_rappel_moteur_sur_verite_terrain() -> None:
    """Le moteur (XSD + règles métier) doit détecter au moins 95 % des anomalies injectées."""
    journal, rapports = _rejouer_verite_terrain()
    metriques = evaluer_detection(journal, rapports)

    print("\nMatrice de rappel du moteur de validation, par code d'erreur :")
    for entree in metriques.as_dict()["par_code"]:
        print(
            f"  {entree['code']} : {entree['detectees']}/{entree['injectees']} "
            f"détectés ({entree['rappel']:.0%})"
        )
    print(
        f"\nRappel global : {metriques.total_detectees}/{metriques.total_anomalies} "
        f"({metriques.rappel_global:.1%})"
    )

    assert metriques.rappel_global >= SEUIL_RAPPEL_MINIMAL, (
        f"Rappel {metriques.rappel_global:.1%} < seuil {SEUIL_RAPPEL_MINIMAL:.0%}"
    )


def test_les_quinze_codes_sont_detectes() -> None:
    """Chacun des 15 codes E001-E015 doit être détecté au moins une fois sur la vérité-terrain."""
    journal, rapports = _rejouer_verite_terrain()
    metriques = evaluer_detection(journal, rapports)

    codes_attendus = {regle.code for regle in REGLES}
    for code in sorted(codes_attendus):
        detectees, injectees = metriques.rappel_par_code.get(code, (0, 0))
        assert injectees > 0, f"Le code {code} n'a jamais été injecté : vérité-terrain incomplète."
        assert detectees > 0, f"Le code {code} n'a jamais été détecté par le moteur."


def test_catalogue_regles_couvre_les_quinze_codes() -> None:
    """Le catalogue publié doit lister exactement les 15 codes, dédupliqués et triés."""
    catalogue = catalogue_regles()
    codes = [entree["code"] for entree in catalogue]

    assert codes == sorted(codes)
    assert len(codes) == len(set(codes))
    assert codes == [f"E{n:03d}" for n in range(1, 16)]
    for entree in catalogue:
        assert entree["severite"] in {"BLOQUANT", "MAJEUR", "MINEUR"}
        assert entree["libelle_fr"]
