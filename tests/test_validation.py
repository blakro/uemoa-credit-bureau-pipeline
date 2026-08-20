"""Tests unitaires de la validation XSD, du registre de règles métier et du moteur (phase 3)."""

from __future__ import annotations

import datetime
import io

import pytest

from bic.generator.anomalies import DeclarationBrute
from bic.generator.export_xml import construire_arbre_xml
from bic.models import Contrat, Declarant, Emprunteur, Situation, TypeEtablissement
from bic.validation.engine import valider_et_charger, valider_fichier
from bic.validation.rules import ContexteFichier, evaluer_regles
from bic.validation.xsd_validator import valider_structure

DECLARANTS_CONNUS = {"BQ000001"}
DATE_ARRETE = datetime.date(2026, 7, 31)


def _champs_emprunteur(**overrides: str) -> dict[str, str]:
    base = {
        "id_emprunteur_source": "EMP000001",
        "type_personne": "PP",
        "nom": "Issoufou",
        "prenom": "Amadou",
        "raison_sociale": "",
        "date_naissance": "1985-04-12",
        "sexe": "M",
        "type_piece": "CNI",
        "numero_piece": "NE-CNI-12345678",
        "nif": "",
        "telephone": "+22790123456",
        "ville": "Niamey",
        "pays": "NE",
    }
    base.update(overrides)
    return base


def _champs_contrat(**overrides: str) -> dict[str, str]:
    base = {
        "id_contrat_source": "CNT000001",
        "id_emprunteur_source": "EMP000001",
        "type_credit": "moyen_terme",
        "date_octroi": "2024-01-15",
        "date_echeance": "2026-01-15",
        "montant_octroye": "1000000.00",
        "devise": "XOF",
        "taux_interet": "8.50",
        "periodicite": "mensuelle",
        "type_garantie": "aucune",
        "montant_garantie": "0.00",
        "date_arrete": "2026-07-31",
        "encours": "400000.00",
        "montant_impaye": "0.00",
        "jours_retard": "0",
        "classification": "sain",
    }
    base.update(overrides)
    return base


def _xml_declaration(declaration: DeclarationBrute) -> bytes:
    arbre = construire_arbre_xml(declaration, horodatage="2026-08-01T00:00:00+00:00")
    buf = io.BytesIO()
    arbre.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()


def _declaration_propre() -> DeclarationBrute:
    return DeclarationBrute(
        code_declarant="BQ000001",
        date_arrete=DATE_ARRETE,
        emprunteurs=[_champs_emprunteur()],
        contrats=[_champs_contrat()],
    )


# ============================= xsd_validator =============================


def test_fichier_propre_passe_la_validation_xsd() -> None:
    """Un fichier de déclaration conforme ne doit produire aucun rejet structurel."""
    assert valider_structure(_xml_declaration(_declaration_propre())) == []


def test_devise_non_xof_rejetee_par_xsd() -> None:
    """Une devise hors énumération (≠ XOF) doit être détectée structurellement (code E006)."""
    declaration = _declaration_propre()
    declaration.contrats[0]["devise"] = "EUR"
    rejets = valider_structure(_xml_declaration(declaration))
    assert any(r.code == "E006" for r in rejets)


def test_telephone_invalide_rejete_par_xsd() -> None:
    """Un téléphone hors format doit être détecté structurellement, sous le code E014."""
    declaration = _declaration_propre()
    declaration.emprunteurs[0]["telephone"] = "0612345678"
    rejets = valider_structure(_xml_declaration(declaration))
    assert any(r.code == "E014" for r in rejets)


def test_personne_morale_avec_champs_vides_passe_la_validation_xsd() -> None:
    """Les champs conditionnellement vides (nom, numero_piece pour une PM) ne sont pas rejetés."""
    declaration = _declaration_propre()
    declaration.emprunteurs[0] = _champs_emprunteur(
        type_personne="PM",
        nom="",
        prenom="",
        raison_sociale="Sahel Distribution SARL",
        date_naissance="",
        sexe="",
        type_piece="",
        numero_piece="",
        nif="NE12345678",
    )
    assert valider_structure(_xml_declaration(declaration)) == []


# ============================= rules =============================


def _contexte(**overrides: object) -> ContexteFichier:
    base = {
        "declarants_connus": DECLARANTS_CONNUS,
        "ids_emprunteurs_connus": {"EMP000001"},
        "date_reference": DATE_ARRETE,
    }
    base.update(overrides)
    return ContexteFichier(**base)  # type: ignore[arg-type]


def test_e001_champ_obligatoire_vide_detecte() -> None:
    champs = _champs_emprunteur(nom="")
    constats = evaluer_regles("emprunteur", champs["id_emprunteur_source"], champs, _contexte())
    assert any(c.code == "E001" for c in constats)


def test_e005_encours_superieur_montant_octroye() -> None:
    champs = _champs_contrat(encours="1500000.00", montant_octroye="1000000.00")
    constats = evaluer_regles("contrat", champs["id_contrat_source"], champs, _contexte())
    assert any(c.code == "E005" for c in constats)


def test_e008_emprunteur_inexistant() -> None:
    champs = _champs_contrat(id_emprunteur_source="EMP999999")
    constats = evaluer_regles("contrat", champs["id_contrat_source"], champs, _contexte())
    assert any(c.code == "E008" for c in constats)


def test_e012_classification_incoherente() -> None:
    champs = _champs_contrat(jours_retard="120", classification="sain")
    constats = evaluer_regles("contrat", champs["id_contrat_source"], champs, _contexte())
    assert any(c.code == "E012" for c in constats)


def test_enregistrement_conforme_ne_produit_aucun_constat() -> None:
    champs = _champs_contrat()
    constats = evaluer_regles("contrat", champs["id_contrat_source"], champs, _contexte())
    assert constats == []


# ============================= engine =============================


def test_engine_accepte_un_fichier_conforme() -> None:
    rapport = valider_fichier(
        _xml_declaration(_declaration_propre()),
        DECLARANTS_CONNUS,
        date_reference=DATE_ARRETE,
        code_declarant_attendu="BQ000001",
    )
    assert rapport.rejets == []
    assert rapport.nombre_contrats_acceptes == 1
    assert rapport.nombre_contrats_rejetes == 0
    assert rapport.taux_acceptation == pytest.approx(1.0)


def test_engine_rejette_un_contrat_avec_anomalie_bloquante() -> None:
    declaration = _declaration_propre()
    declaration.contrats[0]["encours"] = "-50000.00"
    rapport = valider_fichier(
        _xml_declaration(declaration),
        DECLARANTS_CONNUS,
        date_reference=DATE_ARRETE,
        code_declarant_attendu="BQ000001",
    )
    assert rapport.nombre_contrats_rejetes == 1
    assert any(r.code == "E004" for r in rapport.rejets)


def test_engine_accepte_avec_reserve_une_anomalie_majeure() -> None:
    declaration = _declaration_propre()
    declaration.contrats[0]["devise"] = "EUR"
    rapport = valider_fichier(
        _xml_declaration(declaration),
        DECLARANTS_CONNUS,
        date_reference=DATE_ARRETE,
        code_declarant_attendu="BQ000001",
    )
    assert rapport.nombre_contrats_reserve == 1
    assert rapport.nombre_contrats_rejetes == 0


def test_engine_rejette_tout_le_fichier_si_declarant_inconnu() -> None:
    declaration = _declaration_propre()
    declaration.code_declarant_entete = "ZZ999999"
    rapport = valider_fichier(
        _xml_declaration(declaration),
        DECLARANTS_CONNUS,
        date_reference=DATE_ARRETE,
        code_declarant_attendu="BQ000001",
    )
    assert rapport.fichier_rejete is True
    assert any(r.code == "E013" for r in rapport.rejets)


@pytest.mark.integration
def test_engine_charge_uniquement_les_contrats_acceptes_en_base(db_session) -> None:
    """Un contrat accepté est chargé en base ; un contrat rejeté (bloquant) ne l'est pas."""
    db_session.add(
        Declarant(
            code_declarant="BQ000001",
            raison_sociale="Banque Alpha du Sahel",
            type_etablissement=TypeEtablissement.BANQUE,
            pays="NE",
            date_agrement=datetime.date(2010, 1, 1),
        )
    )
    db_session.commit()

    declaration = _declaration_propre()
    declaration.contrats.append(_champs_contrat(id_contrat_source="CNT000002", encours="-1000.00"))

    rapport = valider_et_charger(
        db_session,
        _xml_declaration(declaration),
        DECLARANTS_CONNUS,
        date_reference=DATE_ARRETE,
        code_declarant_attendu="BQ000001",
    )

    assert rapport.nombre_contrats_acceptes == 1
    assert rapport.nombre_contrats_rejetes == 1

    emprunteur = (
        db_session.query(Emprunteur)
        .filter_by(code_declarant="BQ000001", id_emprunteur_source="EMP000001")
        .one()
    )
    assert emprunteur.nom == "Issoufou"

    contrat_accepte = (
        db_session.query(Contrat)
        .filter_by(code_declarant="BQ000001", id_contrat_source="CNT000001")
        .one()
    )
    situation = db_session.query(Situation).filter_by(id_contrat=contrat_accepte.id).one()
    assert float(situation.encours) == pytest.approx(400000.00)

    contrat_rejete = (
        db_session.query(Contrat)
        .filter_by(code_declarant="BQ000001", id_contrat_source="CNT000002")
        .one_or_none()
    )
    assert contrat_rejete is None
