"""Rapport de solvabilité HTML pour un emprunteur consolidé (id_emprunteur_bic), en français."""

from __future__ import annotations

import html
from pathlib import Path


def bande_de_risque(score: int) -> str:
    """Convertit un score (300-850) en bande de risque A (meilleure) à E (pire)."""
    if score >= 750:
        return "A"
    if score >= 700:
        return "B"
    if score >= 650:
        return "C"
    if score >= 600:
        return "D"
    return "E"


def generer_rapport_solvabilite(
    id_emprunteur_bic: str,
    score: int,
    contributions: list[tuple[str, float]],
    engagements: list[dict[str, str]],
    historique_retards: list[dict[str, object]],
) -> str:
    """Génère un rapport de solvabilité HTML autonome pour un emprunteur consolidé."""
    bande = bande_de_risque(score)
    lignes_facteurs = (
        "".join(
            f"<tr><td>{html.escape(nom)}</td><td>{points:+.0f} points</td></tr>"
            for nom, points in contributions[:3]
        )
        or "<tr><td colspan='2'>Aucun facteur disponible.</td></tr>"
    )

    lignes_engagements = (
        "".join(
            "<tr>"
            f"<td>{html.escape(e['code_declarant'])}</td><td>{html.escape(e['type_credit'])}</td>"
            f"<td>{html.escape(e['encours'])}</td><td>{html.escape(e['classification'])}</td>"
            "</tr>"
            for e in engagements
        )
        or "<tr><td colspan='4'>Aucun engagement en cours.</td></tr>"
    )

    lignes_historique = (
        "".join(
            f"<tr><td>{html.escape(str(h['date_arrete']))}</td><td>{html.escape(str(h['jours_retard']))}</td></tr>"
            for h in historique_retards
        )
        or "<tr><td colspan='2'>Aucun historique disponible.</td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Rapport de solvabilité — {html.escape(id_emprunteur_bic)}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.8rem; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; font-size: 0.85rem; }}
  th {{ background: #f2f2f2; }}
  .score {{ font-size: 2.2rem; font-weight: bold; }}
  .bande {{ display: inline-block; padding: 0.2rem 0.7rem; border-radius: 0.3rem;
            background: #eee; font-weight: bold; margin-left: 0.6rem; }}
</style>
</head>
<body>
  <h1>Rapport de solvabilité</h1>
  <p>Emprunteur consolidé : <strong>{html.escape(id_emprunteur_bic)}</strong></p>
  <p><span class="score">{score}</span><span class="bande">Bande {html.escape(bande)}</span></p>

  <h2>Principaux facteurs explicatifs du score</h2>
  <table><tr><th>Variable</th><th>Contribution</th></tr>{lignes_facteurs}</table>

  <h2>Engagements (tous déclarants confondus)</h2>
  <table>
    <tr><th>Déclarant</th><th>Type de crédit</th><th>Encours</th><th>Classification</th></tr>
    {lignes_engagements}
  </table>

  <h2>Historique des retards (12 derniers mois)</h2>
  <table><tr><th>Arrêté</th><th>Jours de retard</th></tr>{lignes_historique}</table>

  <p><em>Document généré à partir de données synthétiques.</em></p>
</body>
</html>
"""


def ecrire_rapport_solvabilite(
    chemin: Path,
    id_emprunteur_bic: str,
    score: int,
    contributions: list[tuple[str, float]],
    engagements: list[dict[str, str]],
    historique_retards: list[dict[str, object]],
) -> None:
    """Écrit le rapport de solvabilité HTML sur disque."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        generer_rapport_solvabilite(
            id_emprunteur_bic, score, contributions, engagements, historique_retards
        ),
        encoding="utf-8",
    )
