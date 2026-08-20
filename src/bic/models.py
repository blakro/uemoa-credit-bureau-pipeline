"""Modèles SQLAlchemy du schéma BIC (déclarant, emprunteur, contrat, situation)."""

from __future__ import annotations

import datetime
import enum

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Classe de base déclarative pour tous les modèles du schéma BIC."""


class TypeEtablissement(enum.StrEnum):
    """Nature juridique du déclarant assujetti."""

    BANQUE = "banque"
    ETABLISSEMENT_FINANCIER = "etablissement_financier"
    SFD = "sfd"


class TypePersonne(enum.StrEnum):
    """Personne physique ou morale."""

    PP = "PP"
    PM = "PM"


class Sexe(enum.StrEnum):
    """Sexe de l'emprunteur, pertinent uniquement pour une personne physique."""

    M = "M"
    F = "F"


class TypePiece(enum.StrEnum):
    """Type de pièce d'identité déclarée pour l'emprunteur."""

    CNI = "CNI"
    PASSEPORT = "PASSEPORT"
    PERMIS = "PERMIS"
    CARTE_CONSULAIRE = "CARTE_CONSULAIRE"


class TypeCredit(enum.StrEnum):
    """Nature du concours accordé."""

    COURT_TERME = "court_terme"
    MOYEN_TERME = "moyen_terme"
    LONG_TERME = "long_terme"
    DECOUVERT = "decouvert"
    CREDIT_BAIL = "credit_bail"
    ENGAGEMENT_SIGNATURE = "engagement_signature"


class Periodicite(enum.StrEnum):
    """Périodicité de remboursement du contrat."""

    MENSUELLE = "mensuelle"
    TRIMESTRIELLE = "trimestrielle"
    SEMESTRIELLE = "semestrielle"
    ANNUELLE = "annuelle"
    IN_FINE = "in_fine"


class TypeGarantie(enum.StrEnum):
    """Nature de la garantie adossée au contrat."""

    HYPOTHEQUE = "hypotheque"
    NANTISSEMENT = "nantissement"
    CAUTION = "caution"
    GAGE = "gage"
    AUCUNE = "aucune"


class Classification(enum.StrEnum):
    """Classification BCEAO de la qualité de l'encours à l'arrêté."""

    SAIN = "sain"
    SENSIBLE = "sensible"
    DOUTEUX = "douteux"
    CONTENTIEUX = "contentieux"


class Declarant(Base):
    """Établissement assujetti (banque, établissement financier, SFD) qui déclare au BIC."""

    __tablename__ = "declarant"

    code_declarant: Mapped[str] = mapped_column(String(8), primary_key=True)
    raison_sociale: Mapped[str] = mapped_column(String(255), nullable=False)
    type_etablissement: Mapped[TypeEtablissement] = mapped_column(nullable=False)
    pays: Mapped[str] = mapped_column(String(2), nullable=False)
    date_agrement: Mapped[datetime.date] = mapped_column(nullable=False)

    emprunteurs: Mapped[list[Emprunteur]] = relationship(back_populates="declarant")
    contrats: Mapped[list[Contrat]] = relationship(back_populates="declarant")


class Emprunteur(Base):
    """Personne physique ou morale bénéficiaire d'un ou plusieurs contrats, chez un déclarant."""

    __tablename__ = "emprunteur"
    __table_args__ = (
        UniqueConstraint("code_declarant", "id_emprunteur_source", name="uq_emprunteur_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_declarant: Mapped[str] = mapped_column(
        ForeignKey("declarant.code_declarant"), nullable=False
    )
    id_emprunteur_source: Mapped[str] = mapped_column(String(50), nullable=False)
    type_personne: Mapped[TypePersonne] = mapped_column(nullable=False)
    nom: Mapped[str | None] = mapped_column(String(100))
    prenom: Mapped[str | None] = mapped_column(String(100))
    raison_sociale: Mapped[str | None] = mapped_column(String(255))
    date_naissance: Mapped[datetime.date | None] = mapped_column()
    sexe: Mapped[Sexe | None] = mapped_column()
    type_piece: Mapped[TypePiece | None] = mapped_column()
    numero_piece: Mapped[str | None] = mapped_column(String(30))
    nif: Mapped[str | None] = mapped_column(String(30))
    telephone: Mapped[str | None] = mapped_column(String(20))
    ville: Mapped[str | None] = mapped_column(String(100))
    pays: Mapped[str | None] = mapped_column(String(2))
    id_emprunteur_bic: Mapped[str | None] = mapped_column(String(20))

    declarant: Mapped[Declarant] = relationship(back_populates="emprunteurs")
    contrats: Mapped[list[Contrat]] = relationship(back_populates="emprunteur")


class Contrat(Base):
    """Concours de crédit accordé par un déclarant à un emprunteur."""

    __tablename__ = "contrat"
    __table_args__ = (
        UniqueConstraint("code_declarant", "id_contrat_source", name="uq_contrat_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_declarant: Mapped[str] = mapped_column(
        ForeignKey("declarant.code_declarant"), nullable=False
    )
    id_contrat_source: Mapped[str] = mapped_column(String(50), nullable=False)
    id_emprunteur: Mapped[int] = mapped_column(ForeignKey("emprunteur.id"), nullable=False)
    type_credit: Mapped[TypeCredit] = mapped_column(nullable=False)
    date_octroi: Mapped[datetime.date] = mapped_column(nullable=False)
    date_echeance: Mapped[datetime.date] = mapped_column(nullable=False)
    montant_octroye: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    devise: Mapped[str] = mapped_column(String(3), nullable=False)
    taux_interet: Mapped[float | None] = mapped_column(Numeric(5, 2))
    periodicite: Mapped[Periodicite | None] = mapped_column()
    type_garantie: Mapped[TypeGarantie | None] = mapped_column()
    montant_garantie: Mapped[float | None] = mapped_column(Numeric(18, 2))

    declarant: Mapped[Declarant] = relationship(back_populates="contrats")
    emprunteur: Mapped[Emprunteur] = relationship(back_populates="contrats")
    situations: Mapped[list[Situation]] = relationship(back_populates="contrat")


class Situation(Base):
    """Photographie mensuelle (arrêté) de l'encours et de la qualité d'un contrat."""

    __tablename__ = "situation"
    __table_args__ = (UniqueConstraint("id_contrat", "date_arrete", name="uq_situation_arrete"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_contrat: Mapped[int] = mapped_column(ForeignKey("contrat.id"), nullable=False)
    date_arrete: Mapped[datetime.date] = mapped_column(nullable=False)
    encours: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    montant_impaye: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    jours_retard: Mapped[int] = mapped_column(nullable=False, default=0)
    classification: Mapped[Classification] = mapped_column(nullable=False)

    contrat: Mapped[Contrat] = relationship(back_populates="situations")
