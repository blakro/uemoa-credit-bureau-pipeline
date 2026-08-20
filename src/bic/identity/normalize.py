"""Normalisation des identités avant comparaison (accents, casse, particules, ponctuation)."""

from __future__ import annotations

import re
import unicodedata

#: Particules courantes à ignorer lors de la comparaison de noms.
_PARTICULES = {"DE", "DU", "DES", "LA", "LE", "EL", "BEN", "BINTI", "BIN", "AL"}
_PONCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_ESPACES = re.compile(r"\s+")


def sans_accents(texte: str) -> str:
    """Retire les diacritiques d'une chaîne (ex. « é » -> « e »)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def normaliser_nom(texte: str | None) -> str:
    """Normalise un nom ou prénom : majuscules, sans accents, sans ponctuation, sans particules."""
    if not texte:
        return ""
    majuscule_sans_accents = sans_accents(texte).upper()
    sans_ponctuation = _PONCTUATION.sub(" ", majuscule_sans_accents)
    mots = [m for m in _ESPACES.split(sans_ponctuation.strip()) if m and m not in _PARTICULES]
    return " ".join(mots)


def normaliser_nom_complet(principal: str | None, secondaire: str | None = None) -> str:
    """Normalise et concatène deux champs de nom (ex. nom + prénom, ou raison sociale seule)."""
    return " ".join(filter(None, (normaliser_nom(principal), normaliser_nom(secondaire))))


def normaliser_identifiant(texte: str | None) -> str:
    """Normalise un numéro de pièce ou un NIF : majuscules, sans espaces ni tirets."""
    if not texte:
        return ""
    return re.sub(r"[\s-]", "", texte.strip().upper())
