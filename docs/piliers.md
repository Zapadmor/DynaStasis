# Les piliers

DynaStasis range la vie hebdomadaire en cinq piliers, chacun une page. Tous sont activables dans `config/user.toml` (`[piliers] actifs`). Les noms sont des conventions : renommez-les mentalement à votre guise, seuls les codes (`FORGE`, `LOGOS`…) sont techniques.

| Pilier | Page | Rôle |
|---|---|---|
| **Journal de bord** | page d'accueil | radar des piliers, score, paliers vers le score parfait, historique sur 13 semaines, emploi du temps |
| **Forge** | `Forge` | objectifs et tâches, finances, projets en cours (phases et cases à cocher) |
| **Logos** | `Logos` | cursus académique (GPA, UV suivies, catalogue) et plan de carrière |
| **Vigueur** | `Vigueur` | charge d'entraînement (CTL/ATL/TSB), HRV, sommeil, pas, journal de séances, records et prédictions |
| **Résonnance** | `Résonnance` | audit hebdomadaire, trimestriel et annuel, notes sur les proches |
| **Système** | `Système` | pauses (gel), synchronisations, thèmes, état de la base, logs, requêtes SQL |

## Saisie quotidienne (barre latérale)

- **Chrono focus** : démarrez / arrêtez une session et taguez-la (`FORGE_ENGAGEMENT`, `FORGE_HARDSKILLS`, `FORGE_PRO`, `LOGOS`, `VIGUEUR`, `RESONNANCE`, `SYSTEME`). Une session multi-tags répartit sa durée à parts égales.
- **Log du jour** : habitudes (lecture, jeûne…). Chaque saisie recalcule les cumuls de la semaine.

## Le score hebdomadaire

Dix critères binaires (validé / non validé), pondérés (`[poids]`), répartis sur quatre axes du radar :

| Axe | Critères |
|---|---|
| Vigueur | entraînement (minutes), séances, pas, sommeil moyen, charge/fraîcheur (TSB ; seuil assoupli en semaine de décharge) |
| Forge | engagement, projets de fond (focus Hard Skills + Pro + Logos) |
| Logos | focus profond selon le mode, projets de fond |
| Résonnance | écran distractif (sous le seuil ou en baisse vs la semaine précédente), clôture (audit rempli et statut social « Connecté/Ressourcé ») |

Les seuils par défaut sont dans `config/user.toml.example`. Les semaines **gelées** (page Système → Pause : voyage, maladie…) sont exclues des médianes et des comparaisons.

**Score global** : moyenne des axes actifs, chacun pris en médiane sur les 4 dernières semaines complètes (hors gel).

## La journée parfaite

Six critères quotidiens, rang de **S** (6/6) à **D** : sport (ou jour de repos planifié), sommeil, pas, focus selon le mode, focus stratégique, écran distractif sous le seuil ou en baisse par rapport au même jour de la semaine précédente. Le rang du jour s'affiche dans la barre latérale.

## Modes

Les semaines peuvent suivre des séquences de modes (par exemple « École » / « Entreprise ») avec des objectifs de focus différents. Les séquences sont enregistrées dans la table `sequences_mode` ; une semaine sans séquence prend le premier mode de la configuration. Voir [configuration](configuration.md#modes).

## Ce qui est automatique, ce qui est manuel

| Donnée | Source automatique | Alternative manuelle |
|---|---|---|
| sport, HRV, sommeil, pas | Intervals.icu | — (les critères Vigueur restent à 0) |
| temps d'écran | ADB | `logos --manual` |
| finances | exports bancaires | onglet Finance de Forge |
| focus, habitudes, objectifs, projets, audits | — | saisie dans l'interface |
