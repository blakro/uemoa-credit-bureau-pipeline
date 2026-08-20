"""Méthodologie de scorecard classique : binning supervisé, WoE/IV, régression logistique, points.

Score = décalage + facteur * logit, avec facteur = PDO / ln(2) et décalage
calé sur `SCORE_REFERENCE` à des odds de `ODDS_REFERENCE`:1. Seules les
variables dont l'IV (Information Value) est entre 0,02 et 0,5 sont retenues.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

PDO = 20
SCORE_REFERENCE = 600
ODDS_REFERENCE = 50
SCORE_MIN = 300
SCORE_MAX = 850
IV_MIN = 0.02
IV_MAX = 0.5
NB_BINS = 5


@dataclass(frozen=True)
class Bin:
    """Un intervalle de binning supervisé pour une variable, avec son WoE (Weight of Evidence)."""

    borne_inf: float
    borne_sup: float
    woe: float


@dataclass(frozen=True)
class VariableScorecard:
    """Une variable retenue dans la scorecard : ses bins WoE, son IV, et son poids de régression."""

    nom: str
    bins: list[Bin]
    iv: float
    coefficient: float


@dataclass(frozen=True)
class Scorecard:
    """Scorecard entraînée : variables retenues, intercept, facteur et décalage de points."""

    variables: list[VariableScorecard]
    intercept: float
    facteur: float
    decalage: float


def _bornes_binning(valeurs: pd.Series, n_bins: int = NB_BINS) -> list[float]:
    """Bornes de binning par quantiles (bornes distinctes uniquement, extrêmes infinies)."""
    quantiles = np.unique(np.quantile(valeurs, np.linspace(0, 1, n_bins + 1)))
    if len(quantiles) < 3:
        quantiles = np.array([valeurs.min(), valeurs.max()])
    bornes = list(quantiles)
    bornes[0] = -np.inf
    bornes[-1] = np.inf
    return bornes


def _calculer_woe_iv(
    valeurs: pd.Series, cible: pd.Series, bornes: list[float]
) -> tuple[list[Bin], float]:
    """Calcule le WoE de chaque bin et l'IV total de la variable."""
    total_bons = max(int((cible == 0).sum()), 1)
    total_mauvais = max(int((cible == 1).sum()), 1)
    bins: list[Bin] = []
    iv_total = 0.0

    for borne_inf, borne_sup in zip(bornes[:-1], bornes[1:], strict=True):
        masque = (valeurs > borne_inf) & (valeurs <= borne_sup)
        bons = max(int(((cible == 0) & masque).sum()), 0.5)
        mauvais = max(int(((cible == 1) & masque).sum()), 0.5)
        part_bons = bons / total_bons
        part_mauvais = mauvais / total_mauvais
        woe = float(np.log(part_bons / part_mauvais))
        iv_total += (part_bons - part_mauvais) * woe
        bins.append(Bin(float(borne_inf), float(borne_sup), woe))

    return bins, iv_total


def _woe_pour_valeur(valeur: float, bins: list[Bin]) -> float:
    """Retourne le WoE du bin auquel appartient `valeur` (bornes extrêmes en clamp)."""
    for b in bins:
        if b.borne_inf < valeur <= b.borne_sup:
            return b.woe
    return bins[-1].woe if valeur > bins[-1].borne_sup else bins[0].woe


def entrainer_scorecard(
    features: pd.DataFrame, colonnes: list[str], cible: str = "defaut"
) -> Scorecard:
    """Entraîne une scorecard : binning + WoE/IV, sélection IV∈[0,02 ; 0,5], régression logit."""
    y = features[cible]
    bins_par_variable: dict[str, list[Bin]] = {}
    iv_par_variable: dict[str, float] = {}

    for colonne in colonnes:
        bornes = _bornes_binning(features[colonne])
        bins, iv = _calculer_woe_iv(features[colonne], y, bornes)
        if IV_MIN <= iv <= IV_MAX:
            bins_par_variable[colonne] = bins
            iv_par_variable[colonne] = iv

    if not bins_par_variable:
        # Repli : si aucune variable n'est dans la plage cible, on garde la plus informative.
        ivs = {
            c: _calculer_woe_iv(features[c], y, _bornes_binning(features[c]))[1] for c in colonnes
        }
        meilleure = max(ivs, key=lambda c: ivs[c])
        bins, iv = _calculer_woe_iv(features[meilleure], y, _bornes_binning(features[meilleure]))
        bins_par_variable[meilleure] = bins
        iv_par_variable[meilleure] = iv

    X_woe = pd.DataFrame(
        {
            colonne: features[colonne].map(lambda v, b=bins: _woe_pour_valeur(v, b))
            for colonne, bins in bins_par_variable.items()
        }
    )

    modele = LogisticRegression()
    modele.fit(X_woe, y)

    facteur = PDO / np.log(2)
    decalage = SCORE_REFERENCE - facteur * np.log(ODDS_REFERENCE)

    variables = [
        VariableScorecard(
            nom=colonne,
            bins=bins_par_variable[colonne],
            iv=iv_par_variable[colonne],
            coefficient=float(coef),
        )
        for colonne, coef in zip(bins_par_variable.keys(), modele.coef_[0], strict=True)
    ]

    return Scorecard(
        variables=variables,
        intercept=float(modele.intercept_[0]),
        facteur=facteur,
        decalage=decalage,
    )


def calculer_score(
    scorecard: Scorecard, observation: dict[str, float]
) -> tuple[int, list[tuple[str, float]]]:
    """Calcule le score (borné 300-850) d'une observation et la contribution de chaque variable."""
    nb_variables = max(len(scorecard.variables), 1)
    contributions: list[tuple[str, float]] = []
    somme_logit = scorecard.intercept

    for variable in scorecard.variables:
        woe = _woe_pour_valeur(observation[variable.nom], variable.bins)
        logit_partiel = variable.coefficient * woe
        somme_logit += logit_partiel
        # `somme_logit` approxime logit(P(défaut)) ; le score croît avec les odds
        # bon/mauvais, donc avec -logit(P(défaut)) : on inverse le signe ici.
        points = -(logit_partiel + scorecard.intercept / nb_variables) * scorecard.facteur
        contributions.append((variable.nom, points))

    score = scorecard.decalage - scorecard.facteur * somme_logit
    score_borne = int(max(SCORE_MIN, min(SCORE_MAX, round(score))))

    contributions.sort(key=lambda c: abs(c[1]), reverse=True)
    return score_borne, contributions
