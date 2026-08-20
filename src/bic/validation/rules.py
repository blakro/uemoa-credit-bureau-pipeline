"""Registre extensible des règles métier de validation d'une déclaration BIC.

Chaque règle est une `RegleMetier` : un code, un libellé, une sévérité, les
champs concernés, un prédicat qui détecte l'anomalie, et un message de
correction pédagogique. Ajouter une règle = ajouter une entrée à `REGLES`,
sans toucher au moteur (`engine.py`).
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Callable
from dataclasses import dataclass, field

_MOTIF_NUMERO_PIECE = re.compile(r"[A-Z]{2}-[A-Z]+-\d{8}")
_MOTIF_TELEPHONE = re.compile(r"\+\d{3}\d{8}")


@dataclass
class ContexteFichier:
    """Contexte partagé entre les règles d'un même fichier de déclaration."""

    declarants_connus: set[str]
    ids_emprunteurs_connus: set[str]
    date_reference: datetime.date
    ids_contrats_vus: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Constat:
    """Une violation de règle métier constatée sur un enregistrement."""

    entite: str
    identifiant: str
    champ: str
    code: str
    severite: str
    valeur_recue: str
    message_correction: str


@dataclass(frozen=True)
class RegleMetier:
    """Une règle métier extensible du registre de validation."""

    code: str
    libelle_fr: str
    severite: str
    entite: str
    champs: tuple[str, ...]
    predicat: Callable[[dict[str, str], ContexteFichier], bool]
    message_correction: Callable[[dict[str, str]], str]
    champ_selecteur: Callable[[dict[str, str]], str] | None = None


def _parse_date(valeur: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(valeur)
    except (ValueError, TypeError):
        return None


def _parse_decimal(valeur: str) -> float | None:
    try:
        return float(valeur)
    except (ValueError, TypeError):
        return None


def _classification_coherente(jours_retard: int, classification: str) -> bool:
    if jours_retard == 0:
        return classification == "sain"
    if jours_retard <= 30:
        return classification == "sensible"
    if jours_retard <= 90:
        return classification == "douteux"
    return classification == "contentieux"


# ============================= Prédicats : emprunteur =============================


def _e001_champ_obligatoire_vide(champs: dict[str, str], _: ContexteFichier) -> bool:
    if champs["type_personne"] == "PP":
        return not champs["nom"].strip()
    return not champs["raison_sociale"].strip()


def _e002_date_naissance_invalide(champs: dict[str, str], _: ContexteFichier) -> bool:
    valeur = champs["date_naissance"]
    return bool(valeur) and _parse_date(valeur) is None


def _e010_numero_piece_invalide(champs: dict[str, str], _: ContexteFichier) -> bool:
    valeur = champs["numero_piece"]
    return bool(valeur) and not _MOTIF_NUMERO_PIECE.fullmatch(valeur)


def _e011_date_naissance_incoherente(champs: dict[str, str], contexte: ContexteFichier) -> bool:
    date_naissance = _parse_date(champs["date_naissance"])
    if date_naissance is None:
        return False
    age_jours = (contexte.date_reference - date_naissance).days
    age_ans = age_jours / 365.25
    return age_ans < 18 or age_ans > 100


def _e014_telephone_invalide(champs: dict[str, str], _: ContexteFichier) -> bool:
    valeur = champs["telephone"]
    return bool(valeur) and not _MOTIF_TELEPHONE.fullmatch(valeur)


def _e015_nif_manquant(champs: dict[str, str], _: ContexteFichier) -> bool:
    return champs["type_personne"] == "PM" and not champs["nif"].strip()


# ============================= Prédicats : contrat =============================


def _e002_date_contrat_invalide(champs: dict[str, str], _: ContexteFichier) -> bool:
    for cle in ("date_octroi", "date_echeance"):
        if champs[cle] and _parse_date(champs[cle]) is None:
            return True
    return False


def _e003_montant_non_numerique(champs: dict[str, str], _: ContexteFichier) -> bool:
    for cle in ("montant_octroye", "encours"):
        if champs[cle] and _parse_decimal(champs[cle]) is None:
            return True
    return False


def _e004_encours_negatif(champs: dict[str, str], _: ContexteFichier) -> bool:
    encours = _parse_decimal(champs["encours"])
    return encours is not None and encours < 0


def _e005_encours_superieur_montant(champs: dict[str, str], _: ContexteFichier) -> bool:
    encours = _parse_decimal(champs["encours"])
    montant = _parse_decimal(champs["montant_octroye"])
    return encours is not None and montant is not None and encours > montant


def _e006_devise_non_autorisee(champs: dict[str, str], _: ContexteFichier) -> bool:
    return champs["devise"] != "XOF"


def _e007_echeance_avant_octroi(champs: dict[str, str], _: ContexteFichier) -> bool:
    octroi = _parse_date(champs["date_octroi"])
    echeance = _parse_date(champs["date_echeance"])
    return octroi is not None and echeance is not None and echeance < octroi


def _e008_emprunteur_inexistant(champs: dict[str, str], contexte: ContexteFichier) -> bool:
    return champs["id_emprunteur_source"] not in contexte.ids_emprunteurs_connus


def _e009_contrat_duplique(champs: dict[str, str], contexte: ContexteFichier) -> bool:
    return champs["id_contrat_source"] in contexte.ids_contrats_vus


def _e012_classification_incoherente(champs: dict[str, str], _: ContexteFichier) -> bool:
    try:
        jours_retard = int(champs["jours_retard"])
    except (ValueError, TypeError):
        return False
    return not _classification_coherente(jours_retard, champs["classification"])


# ============================= Prédicats : en-tête =============================


def _e013_declarant_inconnu(champs: dict[str, str], contexte: ContexteFichier) -> bool:
    return champs["code_declarant"] not in contexte.declarants_connus


# ============================= Sélecteurs de champ fautif =============================


def _champ_e001(champs: dict[str, str]) -> str:
    return "nom" if champs["type_personne"] == "PP" else "raison_sociale"


def _champ_e002_contrat(champs: dict[str, str]) -> str:
    if champs["date_octroi"] and _parse_date(champs["date_octroi"]) is None:
        return "date_octroi"
    return "date_echeance"


def _champ_e003(champs: dict[str, str]) -> str:
    if champs["montant_octroye"] and _parse_decimal(champs["montant_octroye"]) is None:
        return "montant_octroye"
    return "encours"


# ============================= Registre =============================

REGLES: tuple[RegleMetier, ...] = (
    RegleMetier(
        code="E001",
        libelle_fr="Champ obligatoire vide",
        severite="BLOQUANT",
        entite="emprunteur",
        champs=("nom", "raison_sociale"),
        predicat=_e001_champ_obligatoire_vide,
        message_correction=lambda c: (
            f"Le champ « {'nom' if c['type_personne'] == 'PP' else 'raison_sociale'} » est "
            "obligatoire et ne peut pas être vide. Complétez-le avant retransmission."
        ),
        champ_selecteur=_champ_e001,
    ),
    RegleMetier(
        code="E002",
        libelle_fr="Format de date invalide",
        severite="BLOQUANT",
        entite="emprunteur",
        champs=("date_naissance",),
        predicat=_e002_date_naissance_invalide,
        message_correction=lambda c: (
            f"La date de naissance « {c['date_naissance']} » n'est pas valide. "
            "Utilisez le format AAAA-MM-JJ et vérifiez qu'il s'agit d'une date calendaire réelle."
        ),
    ),
    RegleMetier(
        code="E010",
        libelle_fr="Numéro de pièce d'identité au format invalide",
        severite="MAJEUR",
        entite="emprunteur",
        champs=("numero_piece",),
        predicat=_e010_numero_piece_invalide,
        message_correction=lambda c: (
            f"Le numéro de pièce « {c['numero_piece']} » ne respecte pas le format attendu "
            "(ex. NE-CNI-12345678). Corrigez la saisie ou vérifiez le document source."
        ),
    ),
    RegleMetier(
        code="E011",
        libelle_fr="Date de naissance incohérente",
        severite="MAJEUR",
        entite="emprunteur",
        champs=("date_naissance",),
        predicat=_e011_date_naissance_incoherente,
        message_correction=lambda c: (
            f"La date de naissance « {c['date_naissance']} » correspond à un âge invraisemblable "
            "(mineur ou plus de 100 ans). Vérifiez la saisie auprès du dossier client."
        ),
    ),
    RegleMetier(
        code="E014",
        libelle_fr="Téléphone hors format national",
        severite="MINEUR",
        entite="emprunteur",
        champs=("telephone",),
        predicat=_e014_telephone_invalide,
        message_correction=lambda c: (
            f"Le numéro de téléphone « {c['telephone']} » ne respecte pas le format national "
            "attendu (+227XXXXXXXX). Corrigez le numéro avant retransmission."
        ),
    ),
    RegleMetier(
        code="E015",
        libelle_fr="NIF manquant sur une personne morale",
        severite="MAJEUR",
        entite="emprunteur",
        champs=("nif",),
        predicat=_e015_nif_manquant,
        message_correction=lambda c: (
            "Le numéro d'identification fiscale (NIF) est obligatoire pour une personne morale. "
            "Complétez-le avant retransmission."
        ),
    ),
    RegleMetier(
        code="E002",
        libelle_fr="Format de date invalide",
        severite="BLOQUANT",
        entite="contrat",
        champs=("date_octroi", "date_echeance"),
        predicat=_e002_date_contrat_invalide,
        message_correction=lambda c: (
            "Une des dates du contrat (octroi ou échéance) n'est pas valide. "
            "Utilisez le format AAAA-MM-JJ et vérifiez qu'il s'agit d'une date calendaire réelle."
        ),
        champ_selecteur=_champ_e002_contrat,
    ),
    RegleMetier(
        code="E003",
        libelle_fr="Montant non numérique",
        severite="BLOQUANT",
        entite="contrat",
        champs=("montant_octroye", "encours"),
        predicat=_e003_montant_non_numerique,
        message_correction=lambda c: (
            "Le montant octroyé ou l'encours n'est pas une valeur numérique valide. "
            "Vérifiez qu'aucun texte ou caractère spécial ne s'est glissé dans le champ."
        ),
        champ_selecteur=_champ_e003,
    ),
    RegleMetier(
        code="E004",
        libelle_fr="Encours négatif",
        severite="BLOQUANT",
        entite="contrat",
        champs=("encours",),
        predicat=_e004_encours_negatif,
        message_correction=lambda c: (
            f"L'encours ({c['encours']}) est négatif, ce qui est impossible pour un capital "
            "restant dû. Vérifiez le calcul ou l'extraction depuis le système source."
        ),
    ),
    RegleMetier(
        code="E005",
        libelle_fr="Encours supérieur au montant octroyé",
        severite="MAJEUR",
        entite="contrat",
        champs=("encours", "montant_octroye"),
        predicat=_e005_encours_superieur_montant,
        message_correction=lambda c: (
            f"L'encours ({c['encours']}) dépasse le montant octroyé ({c['montant_octroye']}). "
            "Vérifiez que les intérêts courus ne sont pas intégrés à l'encours en capital."
        ),
    ),
    RegleMetier(
        code="E006",
        libelle_fr="Devise non autorisée",
        severite="MAJEUR",
        entite="contrat",
        champs=("devise",),
        predicat=_e006_devise_non_autorisee,
        message_correction=lambda c: (
            f"La devise « {c['devise']} » n'est pas autorisée : seule la devise XOF est acceptée "
            "pour une déclaration UEMOA. Convertissez le montant ou corrigez la devise déclarée."
        ),
    ),
    RegleMetier(
        code="E007",
        libelle_fr="Date d'échéance antérieure à la date d'octroi",
        severite="BLOQUANT",
        entite="contrat",
        champs=("date_octroi", "date_echeance"),
        predicat=_e007_echeance_avant_octroi,
        message_correction=lambda c: (
            f"La date d'échéance ({c['date_echeance']}) est antérieure à la date d'octroi "
            f"({c['date_octroi']}). Vérifiez les dates saisies dans le système source."
        ),
        champ_selecteur=lambda c: "date_echeance",
    ),
    RegleMetier(
        code="E008",
        libelle_fr="Contrat référençant un emprunteur inexistant",
        severite="BLOQUANT",
        entite="contrat",
        champs=("id_emprunteur_source",),
        predicat=_e008_emprunteur_inexistant,
        message_correction=lambda c: (
            f"L'emprunteur « {c['id_emprunteur_source']} » référencé par ce contrat n'existe pas "
            "dans le bloc « emprunteurs » du fichier. Vérifiez l'identifiant ou ajoutez "
            "l'emprunteur manquant."
        ),
    ),
    RegleMetier(
        code="E009",
        libelle_fr="Identifiant de contrat dupliqué",
        severite="BLOQUANT",
        entite="contrat",
        champs=("id_contrat_source",),
        predicat=_e009_contrat_duplique,
        message_correction=lambda c: (
            f"L'identifiant de contrat « {c['id_contrat_source']} » apparaît plusieurs fois dans "
            "ce fichier. Chaque contrat doit avoir un identifiant unique chez le déclarant."
        ),
    ),
    RegleMetier(
        code="E012",
        libelle_fr="Classification incohérente avec les jours de retard",
        severite="MAJEUR",
        entite="contrat",
        champs=("classification", "jours_retard"),
        predicat=_e012_classification_incoherente,
        message_correction=lambda c: (
            f"La classification « {c['classification']} » ne correspond pas aux "
            f"{c['jours_retard']} jours de retard déclarés. Grille attendue : 0j = sain, "
            "1-30j = sensible, 31-90j = douteux, plus de 90j = contentieux."
        ),
    ),
    RegleMetier(
        code="E013",
        libelle_fr="Code déclarant inconnu dans l'en-tête",
        severite="BLOQUANT",
        entite="entete",
        champs=("code_declarant",),
        predicat=_e013_declarant_inconnu,
        message_correction=lambda c: (
            f"Le code déclarant « {c['code_declarant']} » mentionné dans l'en-tête n'est pas "
            "enregistré auprès du BIC. Vérifiez le code ou contactez votre correspondant BIC."
        ),
    ),
)


def regles_pour_entite(entite: str) -> tuple[RegleMetier, ...]:
    """Retourne les règles du registre applicables à une entité donnée."""
    return tuple(regle for regle in REGLES if regle.entite == entite)


def catalogue_regles() -> list[dict[str, str]]:
    """Catalogue dédupliqué des règles, trié par code — pour la documentation et le dashboard.

    Un même code peut être porté par plusieurs règles (E002 vaut pour la date de
    naissance d'un emprunteur comme pour les dates d'un contrat) ; le catalogue
    n'en garde qu'une entrée, en fusionnant les entités concernées.
    """
    par_code: dict[str, dict[str, str]] = {}
    for regle in REGLES:
        entree = par_code.get(regle.code)
        if entree is None:
            par_code[regle.code] = {
                "code": regle.code,
                "libelle_fr": regle.libelle_fr,
                "severite": regle.severite,
                "entites": regle.entite,
            }
        elif regle.entite not in entree["entites"]:
            entree["entites"] = f"{entree['entites']}, {regle.entite}"
    return [par_code[code] for code in sorted(par_code)]


def evaluer_regles(
    entite: str, identifiant: str, champs: dict[str, str], contexte: ContexteFichier
) -> list[Constat]:
    """Applique les règles métier d'une entité à un enregistrement et retourne les constats."""
    constats: list[Constat] = []
    for regle in regles_pour_entite(entite):
        if regle.predicat(champs, contexte):
            champ_concerne = (
                regle.champ_selecteur(champs) if regle.champ_selecteur else regle.champs[0]
            )
            constats.append(
                Constat(
                    entite=entite,
                    identifiant=identifiant,
                    champ=champ_concerne,
                    code=regle.code,
                    severite=regle.severite,
                    valeur_recue=champs.get(champ_concerne, ""),
                    message_correction=regle.message_correction(champs),
                )
            )
    return constats
