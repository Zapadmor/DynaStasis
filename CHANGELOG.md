# Journal des changements

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Pas encore de versions numérotées : les changements sont regroupés par période.

## Non publié

### Ajouté
- `python main.py seed-demo` : base de démonstration entièrement fictive (semaines, habitudes, focus, sport, temps d'écran, finances, objectifs, projet à phases, plan de profil), idempotente, avec garde-fous contre l'écrasement d'une base réelle.
- `DYNASTASIS_DB` : chemin de base configurable ; `docker-compose.demo.yml` pour essayer l'application sans rien configurer.
- `config/user.toml` (modèle `user.toml.example`) : fuseau horaire, piliers actifs, modes, seuils et poids du score, critère « engagement » (libellé et activation), widget externe facultatif.
- Migrations `.py` (`apply(conn)`) en plus des migrations SQL.
- Documentation publique : README, `docs/` (installation, configuration, piliers, architecture, FAQ), CONTRIBUTING.

### Modifié
- Les modes `ecole` / `entreprise` deviennent des codes configurables (migration 004 : conversion vers `ecole` / `entreprise`, levée des contraintes `CHECK`).
- Le critère propre à l'auteur devient le critère générique « engagement » : tag `FORGE_ENGAGEMENT`, colonnes `focus_engagement_min`, `jours_engagement_semaine`, `forge_drill_engagement`, `plan_drill_engagement`, `forge_jours_engagement_mois` (migration 004).
- Les seuils du score ne sont plus codés dans les vues SQL : ils viennent de `score_config` / `modes_config`.
- `docker-compose.yml` : le fichier de secrets est facultatif ; `./config` est monté en lecture seule.
- `today_paris` / `now_paris` deviennent `today_local` / `now_local` (fuseau configurable).

### Supprimé
- Widget audio externe de la barre latérale (réactivable via `[interface] widget_url`).

## Avant la mise en public

- Secrets hors dépôt (`secrets.env`), lockfile `pip-compile`, Dependabot, CI GitHub Actions, Python 3.12.
- Contenu personnel déplacé en base (`profil_contenu`), historique git assaini.
- Migrations numérotées (`PRAGMA user_version`), tests du scoring, du gel hebdomadaire, des habitudes et du focus, couverture dans la CI.
- Onglet « Projets en cours » (projets, phases, tâches).
