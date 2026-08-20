"""Génération déterministe du jeu de données synthétique (emprunteurs, contrats, situations)."""

from __future__ import annotations

import datetime
import random
import unicodedata
from dataclasses import dataclass, replace

from bic.generator._namedata import (
    FORMES_JURIDIQUES_PM,
    NOMS_ENTREPRISE,
    NOMS_FAMILLE,
    PRENOMS_FEMININS,
    PRENOMS_MASCULINS,
    VILLES_NIGER,
)
from bic.generator.profiles import ProfilDeclarant, get_declarant_profiles

#: Dernier arrêté du jeu de données (fin de mois).
DERNIER_ARRETE = datetime.date(2026, 7, 31)
NOMBRE_ARRETES = 12

TYPES_CREDIT: tuple[str, ...] = (
    "court_terme",
    "moyen_terme",
    "long_terme",
    "decouvert",
    "credit_bail",
    "engagement_signature",
)
_DUREE_MOIS_PAR_TYPE: dict[str, tuple[int, int]] = {
    "court_terme": (3, 12),
    "moyen_terme": (13, 48),
    "long_terme": (49, 180),
    "decouvert": (1, 12),
    "credit_bail": (24, 60),
    "engagement_signature": (6, 36),
}
PERIODICITES: tuple[str, ...] = (
    "mensuelle",
    "trimestrielle",
    "semestrielle",
    "annuelle",
    "in_fine",
)
TYPES_GARANTIE: tuple[str, ...] = ("hypotheque", "nantissement", "caution", "gage", "aucune")

_FRACTION_EMPRUNTEURS_DUPLIQUES = 0.15


@dataclass
class EmprunteurRecord:
    """Enregistrement synthétique d'un emprunteur tel que vu par un déclarant donné."""

    code_declarant: str
    id_emprunteur_source: str
    identite_verite: int
    type_personne: str
    nom: str | None
    prenom: str | None
    raison_sociale: str | None
    date_naissance: datetime.date | None
    sexe: str | None
    type_piece: str | None
    numero_piece: str | None
    nif: str | None
    telephone: str | None
    ville: str | None
    pays: str


@dataclass
class ContratRecord:
    """Enregistrement synthétique d'un contrat de crédit."""

    code_declarant: str
    id_contrat_source: str
    id_emprunteur_source: str
    type_credit: str
    date_octroi: datetime.date
    date_echeance: datetime.date
    montant_octroye: float
    devise: str
    taux_interet: float
    periodicite: str
    type_garantie: str
    montant_garantie: float


@dataclass
class SituationRecord:
    """Photographie mensuelle de l'encours et de la qualité d'un contrat."""

    code_declarant: str
    id_contrat_source: str
    date_arrete: datetime.date
    encours: float
    montant_impaye: float
    jours_retard: int
    classification: str


@dataclass
class JeuDeDonnees:
    """Jeu de données synthétique complet, avant assemblage et injection d'anomalies."""

    emprunteurs: list[EmprunteurRecord]
    contrats: list[ContratRecord]
    situations: list[SituationRecord]


def liste_arretes(
    dernier_arrete: datetime.date = DERNIER_ARRETE, n: int = NOMBRE_ARRETES
) -> list[datetime.date]:
    """Retourne les `n` derniers arrêtés mensuels (fin de mois), du plus ancien au plus récent."""
    arretes = []
    annee, mois = dernier_arrete.year, dernier_arrete.month
    for _ in range(n):
        arretes.append(_fin_de_mois(annee, mois))
        mois -= 1
        if mois == 0:
            mois = 12
            annee -= 1
    return list(reversed(arretes))


def _fin_de_mois(annee: int, mois: int) -> datetime.date:
    premier_jour_suivant = (
        datetime.date(annee + 1, 1, 1) if mois == 12 else datetime.date(annee, mois + 1, 1)
    )
    return premier_jour_suivant - datetime.timedelta(days=1)


def _ajouter_mois(d: datetime.date, mois: int) -> datetime.date:
    mois_total = d.month - 1 + mois
    annee = d.year + mois_total // 12
    mois_resultat = mois_total % 12 + 1
    jour_max = _fin_de_mois(annee, mois_resultat).day
    return datetime.date(annee, mois_resultat, min(d.day, jour_max))


def _sans_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def _varier_identite(rng: random.Random, base: EmprunteurRecord) -> EmprunteurRecord:
    """Applique une variation d'orthographe plausible à une identité dupliquée ailleurs."""
    variante = replace(base)
    variation = rng.choice(["accents", "inversion", "initiale", "date_decalee"])
    if variation == "accents" and variante.nom:
        variante.nom = _sans_accents(variante.nom)
        if variante.prenom:
            variante.prenom = _sans_accents(variante.prenom)
    elif variation == "inversion" and variante.nom and variante.prenom:
        variante.nom, variante.prenom = variante.prenom, variante.nom
    elif variation == "initiale" and variante.prenom:
        variante.prenom = f"{variante.prenom[0]}."
    elif variation == "date_decalee" and variante.date_naissance:
        variante.date_naissance = variante.date_naissance + datetime.timedelta(
            days=rng.choice([-1, 1])
        )
    return variante


def _generer_identite_pp(rng: random.Random) -> tuple[str, str, str, datetime.date]:
    sexe = rng.choice(["M", "F"])
    prenom = rng.choice(PRENOMS_MASCULINS if sexe == "M" else PRENOMS_FEMININS)
    nom = rng.choice(NOMS_FAMILLE)
    age_ans = rng.randint(19, 70)
    jours_offset = rng.randint(0, 364)
    date_naissance = DERNIER_ARRETE.replace(
        year=DERNIER_ARRETE.year - age_ans
    ) - datetime.timedelta(days=jours_offset)
    return nom, prenom, sexe, date_naissance


def _generer_numero_piece(rng: random.Random) -> str:
    return f"NE-CNI-{rng.randint(0, 99_999_999):08d}"


def _generer_telephone(rng: random.Random) -> str:
    return f"+227{rng.randint(90_000_000, 99_999_999)}"


def _generer_emprunteur(
    rng: random.Random, code_declarant: str, id_source: str, identite_verite: int
) -> EmprunteurRecord:
    type_personne = "PP" if rng.random() < 0.8 else "PM"
    ville = rng.choice(VILLES_NIGER)
    telephone = _generer_telephone(rng)

    if type_personne == "PP":
        nom, prenom, sexe, date_naissance = _generer_identite_pp(rng)
        return EmprunteurRecord(
            code_declarant=code_declarant,
            id_emprunteur_source=id_source,
            identite_verite=identite_verite,
            type_personne=type_personne,
            nom=nom,
            prenom=prenom,
            raison_sociale=None,
            date_naissance=date_naissance,
            sexe=sexe,
            type_piece="CNI",
            numero_piece=_generer_numero_piece(rng),
            nif=None,
            telephone=telephone,
            ville=ville,
            pays="NE",
        )

    raison_sociale = f"{rng.choice(NOMS_ENTREPRISE)} {rng.choice(FORMES_JURIDIQUES_PM)}"
    return EmprunteurRecord(
        code_declarant=code_declarant,
        id_emprunteur_source=id_source,
        identite_verite=identite_verite,
        type_personne=type_personne,
        nom=None,
        prenom=None,
        raison_sociale=raison_sociale,
        date_naissance=None,
        sexe=None,
        type_piece=None,
        numero_piece=None,
        nif=f"NE{rng.randint(10_000_000, 99_999_999)}",
        telephone=telephone,
        ville=ville,
        pays="NE",
    )


def _generer_emprunteurs(
    rng: random.Random, profiles: list[ProfilDeclarant], n_cible: int
) -> list[EmprunteurRecord]:
    """Génère les emprunteurs, avec ~15 % d'identités dupliquées chez 2 à 4 déclarants."""
    n_base = round(n_cible / (1 + _FRACTION_EMPRUNTEURS_DUPLIQUES * 2))
    emprunteurs: list[EmprunteurRecord] = []
    compteur_par_declarant: dict[str, int] = {}

    def prochain_id(code_declarant: str) -> str:
        compteur_par_declarant[code_declarant] = compteur_par_declarant.get(code_declarant, 0) + 1
        return f"EMP{compteur_par_declarant[code_declarant]:06d}"

    identite_verite = 0
    while identite_verite < n_base:
        declarant_principal = rng.choice(profiles)
        base = _generer_emprunteur(
            rng,
            declarant_principal.code_declarant,
            prochain_id(declarant_principal.code_declarant),
            identite_verite,
        )
        emprunteurs.append(base)

        if rng.random() < _FRACTION_EMPRUNTEURS_DUPLIQUES:
            autres_declarants = [
                p for p in profiles if p.code_declarant != declarant_principal.code_declarant
            ]
            nb_doublons = min(rng.randint(1, 3), len(autres_declarants))
            for declarant_doublon in rng.sample(autres_declarants, k=nb_doublons):
                variante = _varier_identite(rng, base)
                variante.code_declarant = declarant_doublon.code_declarant
                variante.id_emprunteur_source = prochain_id(declarant_doublon.code_declarant)
                emprunteurs.append(variante)

        identite_verite += 1

    while len(emprunteurs) < n_cible:
        declarant = rng.choice(profiles)
        emprunteurs.append(
            _generer_emprunteur(
                rng,
                declarant.code_declarant,
                prochain_id(declarant.code_declarant),
                identite_verite,
            )
        )
        identite_verite += 1

    rng.shuffle(emprunteurs)
    return emprunteurs


def _generer_contrats(
    rng: random.Random, emprunteurs: list[EmprunteurRecord], n_cible: int
) -> list[ContratRecord]:
    """Génère des contrats répartis sur les déclarants, rattachés à leurs propres emprunteurs."""
    emprunteurs_par_declarant: dict[str, list[EmprunteurRecord]] = {}
    for e in emprunteurs:
        emprunteurs_par_declarant.setdefault(e.code_declarant, []).append(e)

    premier_arrete = liste_arretes()[0]
    dernier_arrete = DERNIER_ARRETE
    fenetre_jours = max((dernier_arrete - premier_arrete).days, 1)

    compteur_par_declarant: dict[str, int] = {}
    contrats: list[ContratRecord] = []

    for _ in range(n_cible):
        emprunteur = rng.choice(rng.choice(list(emprunteurs_par_declarant.values())))
        type_credit = rng.choice(TYPES_CREDIT)
        duree_min, duree_max = _DUREE_MOIS_PAR_TYPE[type_credit]
        duree_mois = rng.randint(duree_min, duree_max)

        if rng.random() < 0.5:
            date_octroi = premier_arrete - datetime.timedelta(days=rng.randint(0, 900))
        else:
            date_octroi = premier_arrete + datetime.timedelta(days=rng.randint(0, fenetre_jours))
        date_echeance = _ajouter_mois(date_octroi, duree_mois)

        montant_octroye = round(rng.uniform(200_000, 25_000_000), 2)
        montant_garantie = (
            round(montant_octroye * rng.uniform(0.0, 1.2), 2) if rng.random() < 0.6 else 0.0
        )

        compteur_par_declarant[emprunteur.code_declarant] = (
            compteur_par_declarant.get(emprunteur.code_declarant, 0) + 1
        )
        id_contrat = f"CNT{compteur_par_declarant[emprunteur.code_declarant]:06d}"

        contrats.append(
            ContratRecord(
                code_declarant=emprunteur.code_declarant,
                id_contrat_source=id_contrat,
                id_emprunteur_source=emprunteur.id_emprunteur_source,
                type_credit=type_credit,
                date_octroi=date_octroi,
                date_echeance=date_echeance,
                montant_octroye=montant_octroye,
                devise="XOF",
                taux_interet=round(rng.uniform(5.0, 15.0), 2),
                periodicite=rng.choice(PERIODICITES),
                type_garantie=rng.choice(TYPES_GARANTIE),
                montant_garantie=montant_garantie,
            )
        )

    return contrats


def _classification_depuis_jours_retard(jours_retard: int) -> str:
    """Applique la grille standard : 0j sain, 1-30 sensible, 31-90 douteux, >90 contentieux."""
    if jours_retard == 0:
        return "sain"
    if jours_retard <= 30:
        return "sensible"
    if jours_retard <= 90:
        return "douteux"
    return "contentieux"


def _generer_situations(rng: random.Random, contrats: list[ContratRecord]) -> list[SituationRecord]:
    """Génère les arrêtés mensuels de chaque contrat : amortissement et dynamique d'impayés."""
    situations: list[SituationRecord] = []
    arretes = liste_arretes()

    for contrat in contrats:
        arretes_actifs = [a for a in arretes if contrat.date_octroi <= a <= contrat.date_echeance]
        if not arretes_actifs:
            continue

        duree_totale_jours = max((contrat.date_echeance - contrat.date_octroi).days, 1)
        devient_impaye = rng.random() < 0.20
        mois_debut_impaye = rng.randint(0, len(arretes_actifs) - 1) if devient_impaye else None
        jours_retard = 0

        for indice, arrete in enumerate(arretes_actifs):
            fraction_ecoulee = min((arrete - contrat.date_octroi).days / duree_totale_jours, 1.0)
            encours = max(
                round(contrat.montant_octroye * (1 - fraction_ecoulee) * rng.uniform(0.97, 1.0), 2),
                0.0,
            )

            if devient_impaye and mois_debut_impaye is not None and indice >= mois_debut_impaye:
                jours_retard = min(jours_retard + rng.randint(15, 35), 365)
            else:
                jours_retard = 0

            montant_impaye = (
                round(encours * rng.uniform(0.05, 0.30), 2) if jours_retard > 0 else 0.0
            )

            situations.append(
                SituationRecord(
                    code_declarant=contrat.code_declarant,
                    id_contrat_source=contrat.id_contrat_source,
                    date_arrete=arrete,
                    encours=encours,
                    montant_impaye=montant_impaye,
                    jours_retard=jours_retard,
                    classification=_classification_depuis_jours_retard(jours_retard),
                )
            )

    return situations


def generer_jeu_de_donnees(
    profiles: list[ProfilDeclarant] | None = None,
    seed: int = 42,
    n_emprunteurs: int = 3000,
    n_contrats: int = 5000,
) -> JeuDeDonnees:
    """Génère un jeu de données synthétique complet et déterministe, piloté par `seed`."""
    if profiles is None:
        profiles = get_declarant_profiles()
    rng = random.Random(seed)
    emprunteurs = _generer_emprunteurs(rng, profiles, n_emprunteurs)
    contrats = _generer_contrats(rng, emprunteurs, n_contrats)
    situations = _generer_situations(rng, contrats)
    return JeuDeDonnees(emprunteurs=emprunteurs, contrats=contrats, situations=situations)
