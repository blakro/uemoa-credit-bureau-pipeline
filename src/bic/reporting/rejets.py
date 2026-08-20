"""Génération des rapports de rejets destinés aux déclarants (CSV et HTML), en français."""

from __future__ import annotations

import csv
import html
from pathlib import Path

from bic.validation.engine import RapportValidation

_COLONNES_CSV = (
    "ligne",
    "entite",
    "champ",
    "code",
    "severite",
    "valeur_recue",
    "message_correction",
)


def ecrire_csv_rejets(rapport: RapportValidation, chemin: Path) -> None:
    """Écrit le détail des rejets d'un rapport de validation au format CSV."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_COLONNES_CSV)
        for rejet in rapport.rejets:
            writer.writerow(
                [
                    rejet.identifiant,
                    rejet.entite,
                    rejet.champ,
                    rejet.code,
                    rejet.severite,
                    rejet.valeur_recue,
                    rejet.message_correction,
                ]
            )


def _top_erreurs(rapport: RapportValidation, n: int = 5) -> list[tuple[str, int]]:
    """Retourne les `n` codes d'erreur les plus fréquents, du plus au moins fréquent."""
    compteur: dict[str, int] = {}
    for rejet in rapport.rejets:
        compteur[rejet.code] = compteur.get(rejet.code, 0) + 1
    return sorted(compteur.items(), key=lambda kv: kv[1], reverse=True)[:n]


def generer_rapport_html(rapport: RapportValidation) -> str:
    """Génère un rapport HTML autonome, en français, pour un déclarant et un arrêté donnés."""
    top5 = _top_erreurs(rapport)
    lignes_top5 = "".join(
        f"<tr><td>{html.escape(code)}</td><td>{n}</td></tr>" for code, n in top5
    ) or ("<tr><td colspan='2'>Aucune erreur détectée.</td></tr>")
    lignes_detail = (
        "".join(
            "<tr>"
            f"<td>{html.escape(r.identifiant)}</td><td>{html.escape(r.entite)}</td>"
            f"<td>{html.escape(r.champ)}</td><td>{html.escape(r.code)}</td>"
            f"<td class='severite-{html.escape(r.severite)}'>{html.escape(r.severite)}</td>"
            f"<td>{html.escape(r.valeur_recue)}</td><td>{html.escape(r.message_correction)}</td>"
            "</tr>"
            for r in rapport.rejets
        )
        or "<tr><td colspan='7'>Aucun rejet : le fichier est entièrement conforme.</td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Rapport de validation — {html.escape(rapport.code_declarant)} — {rapport.date_arrete.isoformat()}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.8rem; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; font-size: 0.85rem; }}
  th {{ background: #f2f2f2; }}
  .bandeau {{ display: flex; gap: 2.5rem; margin: 1.2rem 0; flex-wrap: wrap; }}
  .chiffre {{ font-size: 1.7rem; font-weight: bold; }}
  .severite-BLOQUANT {{ color: #b00020; font-weight: bold; }}
  .severite-MAJEUR {{ color: #b06000; }}
  .severite-MINEUR {{ color: #7a7a00; }}
</style>
</head>
<body>
  <h1>Rapport de validation de déclaration BIC</h1>
  <p>Déclarant : <strong>{html.escape(rapport.code_declarant)}</strong> —
     Arrêté : <strong>{rapport.date_arrete.isoformat()}</strong></p>

  <div class="bandeau">
    <div><div class="chiffre">{rapport.taux_acceptation:.1%}</div><div>Taux d'acceptation</div></div>
    <div><div class="chiffre">{rapport.nombre_contrats}</div><div>Contrats déclarés</div></div>
    <div><div class="chiffre">{rapport.nombre_contrats_rejetes}</div><div>Contrats rejetés</div></div>
    <div><div class="chiffre">{rapport.nombre_contrats_reserve}</div><div>Acceptés avec réserve</div></div>
  </div>

  <h2>Top 5 des erreurs</h2>
  <table>
    <tr><th>Code</th><th>Occurrences</th></tr>
    {lignes_top5}
  </table>

  <h2>Détail des rejets</h2>
  <table>
    <tr>
      <th>Ligne</th><th>Entité</th><th>Champ</th><th>Code</th>
      <th>Sévérité</th><th>Valeur reçue</th><th>Message de correction</th>
    </tr>
    {lignes_detail}
  </table>

  <p><em>Document généré automatiquement à partir de données synthétiques.</em></p>
</body>
</html>
"""


def ecrire_rapport_html(rapport: RapportValidation, chemin: Path) -> None:
    """Écrit le rapport HTML autonome sur disque."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(generer_rapport_html(rapport), encoding="utf-8")
