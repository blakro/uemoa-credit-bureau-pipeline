# Avertissement

Ce dépôt est un **projet personnel de démonstration technique**. Il n'est
affilié à, ni approuvé par, aucune institution réelle.

## Données 100 % synthétiques

Toutes les données produites et utilisées par ce projet — déclarants,
emprunteurs, contrats, situations d'encours — sont **entièrement générées
par le code** (`src/bic/generator/`), avec une graine pseudo-aléatoire
explicite. Aucune donnée réelle n'est utilisée, stockée ou publiée.

- Les 12 « déclarants » (« Banque Alpha du Sahel », « SFD Espoir Niamey »,
  etc.) sont des noms inventés. Toute ressemblance avec un établissement
  bancaire, financier ou de microfinance réel de la zone UEMOA est fortuite
  et non intentionnelle.
- Les emprunteurs (noms, numéros de pièce d'identité, numéros de téléphone,
  identifiants fiscaux) sont des identités fictives générées
  algorithmiquement. Aucun numéro de pièce ou de téléphone généré ne
  correspond à une personne réelle.
- Les montants, encours, taux et historiques de retard sont simulés selon
  des règles de dynamique de crédit plausibles, mais ne reflètent aucun
  portefeuille réel.

## Schéma de déclaration

Le schéma XML (`schemas/declaration_bic_v1.xsd`) et les règles de
validation métier s'inspirent des **principes généraux** de déclaration à
une centrale des risques de la zone UEMOA (arrêté mensuel, classification
sain/sensible/douteux/contentieux, notion de déclarant assujetti). Ils ne
reproduisent **aucun format d'échange propriétaire** d'une institution
réelle (BCEAO, Creditinfo, ou autre) et n'ont pas vocation à être utilisés
en dehors de ce projet de démonstration.

## Usage

Ce dépôt est fourni à des fins de démonstration technique uniquement. Il ne
doit pas être utilisé pour prendre des décisions de crédit réelles, ni
présenté comme un système de production.
