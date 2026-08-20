# Contexte projet

Simulation du pipeline de déclaration à un Bureau d'Information sur le
Crédit (BIC) de la zone UEMOA. Projet portfolio pour une candidature
d'analyste de données. Toutes les données sont SYNTHÉTIQUES et générées
par le code : aucune donnée réelle, aucun établissement réel.

## Contraintes d'environnement — IMPÉRATIF
- L'utilisateur n'a AUCUN environnement local. Ne propose jamais
  "lance docker", "installe X sur ta machine", "ouvre pgAdmin".
- Tout doit tourner soit dans ce sandbox, soit dans GitHub Actions,
  soit sur GitHub Pages.
- MySQL 8 n'existe QUE dans GitHub Actions (service container).
  En sandbox, les tests d'intégration sont skippés.

## Stack imposée
Python 3.11 · SQLAlchemy 2.x (dialecte MySQL 8, driver PyMySQL) ·
lxml (XSD) · pandas · RapidFuzz · scikit-learn · pytest · Chart.js
(dashboard statique).

## Règles de travail
- Tests AVANT implémentation pour chaque module.
- Commits atomiques, messages en anglais, format Conventional Commits.
- Ne jamais committer le contenu de `data/generated/`.
- Tout message destiné à un utilisateur final (rapport de rejet,
  dashboard) est rédigé EN FRANÇAIS. Le code et les commits en anglais.
- Docstrings sur toute fonction publique.
- Ne crée pas de fichiers de documentation non demandés.

## Vocabulaire métier
- Déclarant : établissement assujetti (banque, EF, SFD) qui transmet
  ses encours au BIC.
- Arrêté : date de photographie des encours (mensuel).
- Encours : capital restant dû.
- Classification : sain / sensible / douteux / contentieux.
- Rejet : enregistrement refusé à l'entrée pour non-conformité.
