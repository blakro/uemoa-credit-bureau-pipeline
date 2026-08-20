"""Test décisif : rejoue la vérité-terrain d'anomalies (phase 2) et mesure le rappel du moteur."""

from __future__ import annotations

import io
from collections import Counter

from bic.generator.anomalies import assembler_declarations, injecter_anomalies
from bic.generator.export_xml import construire_arbre_xml
from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import DERNIER_ARRETE, generer_jeu_de_donnees
from bic.validation.engine import valider_fichier

SEUIL_RAPPEL_MINIMAL = 0.95


def test_rappel_moteur_sur_verite_terrain() -> None:
    """Le moteur (XSD + règles métier) doit détecter au moins 95 % des anomalies injectées."""
    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(profiles=profiles, seed=42, n_emprunteurs=1500, n_contrats=2500)
    declarations = assembler_declarations(jeu)
    declarations, journal = injecter_anomalies(declarations, profiles, seed=42)
    declarants_connus = {p.code_declarant for p in profiles}

    verite_terrain = {(a.code_declarant, a.entite, a.ligne, a.champ, a.code) for a in journal}

    detections: set[tuple[str, str, str, str, str]] = set()
    for declaration in declarations:
        arbre = construire_arbre_xml(declaration)
        buf = io.BytesIO()
        arbre.write(buf, encoding="utf-8", xml_declaration=True)
        rapport = valider_fichier(
            buf.getvalue(),
            declarants_connus,
            date_reference=DERNIER_ARRETE,
            code_declarant_attendu=declaration.code_declarant,
        )
        for rejet in rapport.rejets:
            detections.add(
                (rejet.code_declarant, rejet.entite, rejet.identifiant, rejet.champ, rejet.code)
            )

    vrais_positifs = verite_terrain & detections
    faux_negatifs = verite_terrain - detections
    rappel_global = len(vrais_positifs) / len(verite_terrain)

    par_code_total = Counter(a[4] for a in verite_terrain)
    par_code_detecte = Counter(a[4] for a in vrais_positifs)

    print("\nMatrice de rappel du moteur de validation, par code d'erreur :")
    for code in sorted(par_code_total):
        total = par_code_total[code]
        detecte = par_code_detecte.get(code, 0)
        print(f"  {code} : {detecte}/{total} détectés ({detecte / total:.0%})")
    print(f"\nRappel global : {len(vrais_positifs)}/{len(verite_terrain)} ({rappel_global:.1%})")
    if faux_negatifs:
        print(f"Exemples de faux négatifs (max 5) : {list(faux_negatifs)[:5]}")

    assert rappel_global >= SEUIL_RAPPEL_MINIMAL, (
        f"Rappel {rappel_global:.1%} < seuil {SEUIL_RAPPEL_MINIMAL:.0%}"
    )
