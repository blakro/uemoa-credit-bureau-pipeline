"""Export des fichiers de déclaration BIC au format XML, un par déclarant et par arrêté."""

from __future__ import annotations

import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from bic.generator.anomalies import DeclarationBrute


def _horodatage() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def construire_arbre_xml(
    declaration: DeclarationBrute, horodatage: str | None = None
) -> ElementTree:
    """Construit l'arbre XML d'un fichier de déclaration (en-tête, emprunteurs, contrats)."""
    racine = Element("declaration")

    entete = SubElement(racine, "entete")
    SubElement(entete, "code_declarant").text = (
        declaration.code_declarant_entete or declaration.code_declarant
    )
    SubElement(entete, "date_arrete").text = declaration.date_arrete.isoformat()
    SubElement(entete, "nombre_enregistrements").text = str(
        len(declaration.emprunteurs) + len(declaration.contrats)
    )
    SubElement(entete, "horodatage").text = horodatage or _horodatage()

    emprunteurs_el = SubElement(racine, "emprunteurs")
    for champs in declaration.emprunteurs:
        emprunteur_el = SubElement(emprunteurs_el, "emprunteur")
        for nom_champ, valeur in champs.items():
            SubElement(emprunteur_el, nom_champ).text = valeur

    contrats_el = SubElement(racine, "contrats")
    for champs in declaration.contrats:
        contrat_el = SubElement(contrats_el, "contrat")
        for nom_champ, valeur in champs.items():
            SubElement(contrat_el, nom_champ).text = valeur

    arbre = ElementTree(racine)
    indent(arbre, space="  ")
    return arbre


def nom_fichier(declaration: DeclarationBrute) -> str:
    """Nom de fichier standard : ``<code_declarant>_<AAAAMMJJ>.xml``."""
    return f"{declaration.code_declarant}_{declaration.date_arrete.strftime('%Y%m%d')}.xml"


def exporter_declarations(declarations: list[DeclarationBrute], dossier_sortie: Path) -> list[Path]:
    """Écrit un fichier XML par déclaration dans `dossier_sortie`, retourne les chemins écrits."""
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    chemins: list[Path] = []
    for declaration in declarations:
        arbre = construire_arbre_xml(declaration)
        chemin = dossier_sortie / nom_fichier(declaration)
        arbre.write(chemin, encoding="utf-8", xml_declaration=True)
        chemins.append(chemin)
    return chemins
