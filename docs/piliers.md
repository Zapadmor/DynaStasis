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

## Ajouter un pilier

Un pilier est un module de `src/pillars/` ; ni `main.py` ni `ui_main.py` ne changent.

1. Créez la vue `src/app/views/mon_pilier.py` (ou un paquet si elle a plusieurs onglets) avec une fonction `render()`. Gardez le SQL dans `src/repositories/` et les règles dans `src/services/` (voir [architecture](architecture.md#couches)).
2. Créez `src/pillars/mon_pilier.py` :

   ```python
   from src.pillars.base import Command, Pilier


   def render(cw: dict | None) -> None:
       from src.app.views import mon_pilier  # import paresseux

       mon_pilier.render()


   PILIER = Pilier(
       key="MON_PILIER",            # code technique (config, tags de focus)
       label="Mon pilier",
       icon=":material/star:",
       url_path="mon-pilier",
       render=render,
       # facultatif : une commande de synchro et les sources qu'`main.py sync` lance
       # sync=Command("mon-pilier", "Synchronise ma source", _sync),
       # sources=_sources,
   )
   ```
3. Ajoutez `"mon_pilier"` à `_MODULES` dans `src/pillars/__init__.py` (l'ordre est celui de la navigation).
4. Documentez-le dans cette page et ajoutez un test (`tests/test_piliers.py` vérifie déjà l'ordre, le filtrage par la configuration et l'unicité des commandes).

Le pilier apparaît alors dans `[piliers] actifs` (activé par défaut), dans la navigation et, s'il déclare `sync` ou `sources`, dans `python main.py --help` et `python main.py sync`.
