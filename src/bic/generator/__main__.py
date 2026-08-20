"""CLI de génération : ``python -m bic.generator --seed 42 --output data/generated/``."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from bic.generator.anomalies import assembler_declarations, injecter_anomalies
from bic.generator.export_xml import exporter_declarations
from bic.generator.profiles import get_declarant_profiles
from bic.generator.synthetic import generer_jeu_de_donnees


def _analyser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Génère un jeu de données synthétique de déclaration BIC (aucune donnée réelle)."
        )
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Graine du générateur pseudo-aléatoire."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/generated"), help="Dossier de sortie."
    )
    parser.add_argument("--n-emprunteurs", type=int, default=3000)
    parser.add_argument("--n-contrats", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    """Génère le jeu de données, l'assemble en déclarations, injecte des anomalies et exporte."""
    args = _analyser_arguments()

    profiles = get_declarant_profiles()
    jeu = generer_jeu_de_donnees(
        profiles=profiles,
        seed=args.seed,
        n_emprunteurs=args.n_emprunteurs,
        n_contrats=args.n_contrats,
    )
    declarations = assembler_declarations(jeu)
    declarations, journal = injecter_anomalies(declarations, profiles, seed=args.seed)

    dossier_declarations = args.output / "declarations"
    fichiers = exporter_declarations(declarations, dossier_declarations)

    args.output.mkdir(parents=True, exist_ok=True)

    chemin_verite_anomalies = args.output / "ground_truth_anomalies.csv"
    with chemin_verite_anomalies.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["declarant", "entite", "ligne", "champ", "code"])
        for anomalie in journal:
            writer.writerow(
                [
                    anomalie.code_declarant,
                    anomalie.entite,
                    anomalie.ligne,
                    anomalie.champ,
                    anomalie.code,
                ]
            )

    chemin_verite_identite = args.output / "identity_ground_truth.csv"
    with chemin_verite_identite.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["code_declarant", "id_emprunteur_source", "identite_verite"])
        for emprunteur in jeu.emprunteurs:
            writer.writerow(
                [
                    emprunteur.code_declarant,
                    emprunteur.id_emprunteur_source,
                    emprunteur.identite_verite,
                ]
            )

    print(
        f"{len(jeu.emprunteurs)} emprunteurs, {len(jeu.contrats)} contrats, "
        f"{len(jeu.situations)} situations générés."
    )
    print(f"{len(fichiers)} fichiers de déclaration écrits dans {dossier_declarations}")
    print(f"{len(journal)} anomalies injectées, journal : {chemin_verite_anomalies}")
    print(f"Vérité-terrain d'identité : {chemin_verite_identite}")


if __name__ == "__main__":
    main()
