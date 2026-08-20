"""Orchestration : XML -> validation XSD -> règles métier -> décision -> chargement -> rapport."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session

from bic.models import (
    Classification,
    Contrat,
    Emprunteur,
    Periodicite,
    Sexe,
    Situation,
    TypeCredit,
    TypeGarantie,
    TypePersonne,
    TypePiece,
)
from bic.validation.rules import REGLES, ContexteFichier, evaluer_regles
from bic.validation.xsd_validator import valider_structure

#: Sévérité associée à chaque code, dérivée du registre de règles métier.
_SEVERITE_PAR_CODE: dict[str, str] = {}
for _regle in REGLES:
    _SEVERITE_PAR_CODE.setdefault(_regle.code, _regle.severite)


@dataclass(frozen=True)
class RejetRapport:
    """Un rejet consolidé (structurel ou métier), prêt pour le reporting."""

    code_declarant: str
    date_arrete: datetime.date
    entite: str
    identifiant: str
    champ: str
    code: str
    severite: str
    valeur_recue: str
    message_correction: str


@dataclass
class RapportValidation:
    """Résultat de la validation (et éventuellement du chargement) d'un fichier de déclaration."""

    code_declarant: str
    date_arrete: datetime.date
    nombre_emprunteurs: int
    nombre_contrats: int
    nombre_contrats_acceptes: int
    nombre_contrats_reserve: int
    nombre_contrats_rejetes: int
    fichier_rejete: bool
    rejets: list[RejetRapport] = field(default_factory=list)

    @property
    def taux_acceptation(self) -> float:
        """Part des contrats acceptés (sans ou avec réserve) parmi les contrats du fichier."""
        if self.nombre_contrats == 0:
            return 0.0
        return (self.nombre_contrats_acceptes + self.nombre_contrats_reserve) / self.nombre_contrats


def _element_vers_champs(element: etree._Element) -> dict[str, str]:
    return {enfant.tag: (enfant.text or "") for enfant in element}


def _decision(severites: list[str]) -> str:
    if "BLOQUANT" in severites:
        return "REJETE"
    if severites:
        return "ACCEPTE_AVEC_RESERVE"
    return "ACCEPTE"


def _valider(
    contenu_xml: bytes,
    declarants_connus: set[str],
    date_reference: datetime.date | None,
    code_declarant_attendu: str | None = None,
) -> tuple[RapportValidation, dict[str, str], list[dict[str, str]], list[dict[str, str]]]:
    """Exécute la validation XSD + règles métier, retourne le rapport et les données parsées."""
    rejets_structurels = valider_structure(contenu_xml)

    if rejets_structurels and rejets_structurels[0].code == "E000":
        erreur = rejets_structurels[0]
        rapport = RapportValidation(
            code_declarant="?",
            date_arrete=date_reference or datetime.date.today(),
            nombre_emprunteurs=0,
            nombre_contrats=0,
            nombre_contrats_acceptes=0,
            nombre_contrats_reserve=0,
            nombre_contrats_rejetes=0,
            fichier_rejete=True,
            rejets=[
                RejetRapport(
                    code_declarant="?",
                    date_arrete=date_reference or datetime.date.today(),
                    entite="fichier",
                    identifiant="?",
                    champ="?",
                    code="E000",
                    severite="BLOQUANT",
                    valeur_recue="",
                    message_correction=erreur.message,
                )
            ],
        )
        return rapport, {}, [], []

    racine = etree.fromstring(contenu_xml)
    entete = _element_vers_champs(racine.find("entete"))
    # Identité réellement connue (canal de transmission) : peut différer du contenu de
    # l'en-tête si celui-ci est corrompu, ce qui est précisément ce que détecte E013.
    code_declarant_reel = code_declarant_attendu or entete["code_declarant"]
    date_arrete = datetime.date.fromisoformat(entete["date_arrete"])

    emprunteurs = [_element_vers_champs(el) for el in racine.find("emprunteurs")]
    contrats = [_element_vers_champs(el) for el in racine.find("contrats")]

    contexte = ContexteFichier(
        declarants_connus=declarants_connus,
        ids_emprunteurs_connus={e["id_emprunteur_source"] for e in emprunteurs},
        date_reference=date_reference or date_arrete,
    )

    # Les codes E001-E015 sont ré-évalués ci-dessous par les règles métier avec le bon
    # contexte (entité, identifiant) ; on ne garde ici que les rejets structurels
    # que les règles métier ne couvrent pas, pour éviter un double comptage.
    rejets: list[RejetRapport] = [
        RejetRapport(
            code_declarant=code_declarant_reel,
            date_arrete=date_arrete,
            entite="fichier",
            identifiant="?",
            champ="?",
            code=r.code,
            severite=_SEVERITE_PAR_CODE.get(r.code, "BLOQUANT"),
            valeur_recue="",
            message_correction=r.message,
        )
        for r in rejets_structurels
        if r.code not in _SEVERITE_PAR_CODE
    ]

    severites_par_id: dict[str, list[str]] = {}

    for constat in evaluer_regles("entete", code_declarant_reel, entete, contexte):
        rejets.append(
            RejetRapport(
                code_declarant=code_declarant_reel,
                date_arrete=date_arrete,
                entite=constat.entite,
                identifiant=constat.identifiant,
                champ=constat.champ,
                code=constat.code,
                severite=constat.severite,
                valeur_recue=constat.valeur_recue,
                message_correction=constat.message_correction,
            )
        )
    entete_rejetee = any(r.severite == "BLOQUANT" for r in rejets if r.entite == "entete")

    for champs_emprunteur in emprunteurs:
        id_emp = champs_emprunteur["id_emprunteur_source"]
        constats = evaluer_regles("emprunteur", id_emp, champs_emprunteur, contexte)
        severites_par_id.setdefault(id_emp, [])
        for constat in constats:
            severites_par_id[id_emp].append(constat.severite)
            rejets.append(
                RejetRapport(
                    code_declarant=code_declarant_reel,
                    date_arrete=date_arrete,
                    entite=constat.entite,
                    identifiant=constat.identifiant,
                    champ=constat.champ,
                    code=constat.code,
                    severite=constat.severite,
                    valeur_recue=constat.valeur_recue,
                    message_correction=constat.message_correction,
                )
            )

    for champs_contrat in contrats:
        id_contrat = champs_contrat["id_contrat_source"]
        constats = evaluer_regles("contrat", id_contrat, champs_contrat, contexte)
        severites_par_id.setdefault(id_contrat, [])
        for constat in constats:
            severites_par_id[id_contrat].append(constat.severite)
            rejets.append(
                RejetRapport(
                    code_declarant=code_declarant_reel,
                    date_arrete=date_arrete,
                    entite=constat.entite,
                    identifiant=constat.identifiant,
                    champ=constat.champ,
                    code=constat.code,
                    severite=constat.severite,
                    valeur_recue=constat.valeur_recue,
                    message_correction=constat.message_correction,
                )
            )
        contexte.ids_contrats_vus.add(id_contrat)

    decisions = {
        identifiant: ("REJETE" if entete_rejetee else _decision(severites))
        for identifiant, severites in severites_par_id.items()
    }

    nombre_acceptes = sum(1 for c in contrats if decisions[c["id_contrat_source"]] == "ACCEPTE")
    nombre_reserve = sum(
        1 for c in contrats if decisions[c["id_contrat_source"]] == "ACCEPTE_AVEC_RESERVE"
    )
    nombre_rejetes = sum(1 for c in contrats if decisions[c["id_contrat_source"]] == "REJETE")

    rapport = RapportValidation(
        code_declarant=code_declarant_reel,
        date_arrete=date_arrete,
        nombre_emprunteurs=len(emprunteurs),
        nombre_contrats=len(contrats),
        nombre_contrats_acceptes=nombre_acceptes,
        nombre_contrats_reserve=nombre_reserve,
        nombre_contrats_rejetes=nombre_rejetes,
        fichier_rejete=entete_rejetee,
        rejets=rejets,
    )

    if entete_rejetee:
        return rapport, decisions, [], []
    return rapport, decisions, emprunteurs, contrats


def valider_fichier(
    contenu_xml: bytes,
    declarants_connus: set[str],
    date_reference: datetime.date | None = None,
    code_declarant_attendu: str | None = None,
) -> RapportValidation:
    """Valide un fichier de déclaration (XSD + règles métier) sans le charger en base.

    `code_declarant_attendu` est l'identité du déclarant connue du canal de
    transmission (ex. compte SFTP, clé API) : elle peut différer du contenu
    de l'en-tête si celui-ci est corrompu (voir E013).
    """
    rapport, _decisions, _emprunteurs, _contrats = _valider(
        contenu_xml, declarants_connus, date_reference, code_declarant_attendu
    )
    return rapport


def _get_ou_creer_emprunteur(
    session: Session, code_declarant: str, champs: dict[str, str]
) -> Emprunteur:
    existant = session.execute(
        select(Emprunteur).where(
            Emprunteur.code_declarant == code_declarant,
            Emprunteur.id_emprunteur_source == champs["id_emprunteur_source"],
        )
    ).scalar_one_or_none()
    if existant is not None:
        return existant

    emprunteur = Emprunteur(
        code_declarant=code_declarant,
        id_emprunteur_source=champs["id_emprunteur_source"],
        type_personne=TypePersonne(champs["type_personne"]),
        nom=champs["nom"] or None,
        prenom=champs["prenom"] or None,
        raison_sociale=champs["raison_sociale"] or None,
        date_naissance=datetime.date.fromisoformat(champs["date_naissance"])
        if champs["date_naissance"]
        else None,
        sexe=Sexe(champs["sexe"]) if champs["sexe"] else None,
        type_piece=TypePiece(champs["type_piece"]) if champs["type_piece"] else None,
        numero_piece=champs["numero_piece"] or None,
        nif=champs["nif"] or None,
        telephone=champs["telephone"] or None,
        ville=champs["ville"] or None,
        pays=champs["pays"],
    )
    session.add(emprunteur)
    session.flush()
    return emprunteur


def _get_ou_creer_contrat(
    session: Session, code_declarant: str, emprunteur: Emprunteur, champs: dict[str, str]
) -> Contrat:
    existant = session.execute(
        select(Contrat).where(
            Contrat.code_declarant == code_declarant,
            Contrat.id_contrat_source == champs["id_contrat_source"],
        )
    ).scalar_one_or_none()
    if existant is not None:
        return existant

    contrat = Contrat(
        code_declarant=code_declarant,
        id_contrat_source=champs["id_contrat_source"],
        id_emprunteur=emprunteur.id,
        type_credit=TypeCredit(champs["type_credit"]),
        date_octroi=datetime.date.fromisoformat(champs["date_octroi"]),
        date_echeance=datetime.date.fromisoformat(champs["date_echeance"]),
        montant_octroye=float(champs["montant_octroye"]),
        devise=champs["devise"],
        taux_interet=float(champs["taux_interet"]) if champs["taux_interet"] else None,
        periodicite=Periodicite(champs["periodicite"]) if champs["periodicite"] else None,
        type_garantie=TypeGarantie(champs["type_garantie"]) if champs["type_garantie"] else None,
        montant_garantie=float(champs["montant_garantie"]) if champs["montant_garantie"] else None,
    )
    session.add(contrat)
    session.flush()
    return contrat


def _creer_situation(session: Session, contrat: Contrat, champs: dict[str, str]) -> None:
    existante = session.execute(
        select(Situation).where(
            Situation.id_contrat == contrat.id,
            Situation.date_arrete == datetime.date.fromisoformat(champs["date_arrete"]),
        )
    ).scalar_one_or_none()
    if existante is not None:
        return

    session.add(
        Situation(
            id_contrat=contrat.id,
            date_arrete=datetime.date.fromisoformat(champs["date_arrete"]),
            encours=float(champs["encours"]),
            montant_impaye=float(champs["montant_impaye"]),
            jours_retard=int(champs["jours_retard"]),
            classification=Classification(champs["classification"]),
        )
    )


def valider_et_charger(
    session: Session,
    contenu_xml: bytes,
    declarants_connus: set[str],
    date_reference: datetime.date | None = None,
    code_declarant_attendu: str | None = None,
) -> RapportValidation:
    """Valide un fichier de déclaration et charge en base les enregistrements acceptés."""
    rapport, decisions, emprunteurs, contrats = _valider(
        contenu_xml, declarants_connus, date_reference, code_declarant_attendu
    )
    if rapport.fichier_rejete:
        return rapport

    emprunteurs_par_id = {e["id_emprunteur_source"]: e for e in emprunteurs}
    emprunteurs_charges: dict[str, Emprunteur] = {}

    for champs_contrat in contrats:
        if decisions[champs_contrat["id_contrat_source"]] == "REJETE":
            continue

        id_emp = champs_contrat["id_emprunteur_source"]
        if id_emp not in emprunteurs_charges:
            champs_emprunteur = emprunteurs_par_id.get(id_emp)
            if champs_emprunteur is None:
                continue
            emprunteurs_charges[id_emp] = _get_ou_creer_emprunteur(
                session, rapport.code_declarant, champs_emprunteur
            )

        contrat = _get_ou_creer_contrat(
            session, rapport.code_declarant, emprunteurs_charges[id_emp], champs_contrat
        )
        _creer_situation(session, contrat, champs_contrat)

    session.commit()
    return rapport
