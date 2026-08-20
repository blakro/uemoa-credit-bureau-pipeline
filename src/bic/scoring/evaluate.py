"""Évaluation du modèle de scoring : AUC, Gini, KS, courbe ROC, table de gains par décile."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split


@dataclass
class ResultatEvaluation:
    """Métriques de performance du modèle de scoring sur un échantillon."""

    auc: float
    gini: float
    ks: float
    taux_fpr: list[float]
    taux_tpr: list[float]
    table_gains: pd.DataFrame = field(repr=False)


def separer_train_test(
    features: pd.DataFrame, cible: str = "defaut", test_size: float = 0.3, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split stratifié train/test sur la variable cible."""
    return train_test_split(
        features, test_size=test_size, stratify=features[cible], random_state=seed
    )


def evaluer(scores: pd.Series, cible: pd.Series) -> ResultatEvaluation:
    """Calcule AUC, Gini, KS et la table de gains par décile de score.

    Le score représente la solvabilité (plus élevé = moins risqué) : on
    utilise son opposé pour le calcul de l'AUC, qui mesure la séparation
    vis-à-vis d'une probabilité de défaut croissante.
    """
    auc = float(roc_auc_score(cible, -scores))
    gini = 2 * auc - 1
    fpr, tpr, _ = roc_curve(cible, -scores)
    ks = float(np.max(tpr - fpr))

    table = pd.DataFrame({"score": scores.to_numpy(), "defaut": cible.to_numpy()})
    table["decile"] = pd.qcut(table["score"], 10, labels=False, duplicates="drop")
    table_gains = (
        table.groupby("decile")
        .agg(nb_emprunteurs=("defaut", "count"), nb_defauts=("defaut", "sum"))
        .assign(taux_defaut=lambda d: d["nb_defauts"] / d["nb_emprunteurs"])
        .sort_index(ascending=False)
    )

    return ResultatEvaluation(
        auc=auc,
        gini=gini,
        ks=ks,
        taux_fpr=fpr.tolist(),
        taux_tpr=tpr.tolist(),
        table_gains=table_gains,
    )
