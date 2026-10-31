# Journal des changements

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Pas encore de versions numérotées : les changements sont regroupés par période.

## Non publié

### Ajouté
- `python main.py seed-demo` : base de démonstration entièrement fictive (semaines, habitudes, focus, sport, temps d'écran, finances, objectifs, projet à phases, plan de profil), idempotente, avec garde-fous contre l'écrasement d'une base réelle.
- `DYNASTASIS_DB` : chemin de base configurable ; `docker-compose.demo.yml` pour essayer l'application sans rien configurer.
- `config/user.toml` (modèle `user.toml.example`) : fuseau horaire, piliers actifs, modes, seuils et poids du score, critère « engagement » (libellé et activation), widget externe facultatif.
- Migrations `.py` (`apply(conn)`) en plus des migrations SQL.
- Documentation publique : README, `docs/` (installation, configuration, piliers, architecture, FAQ), CONTRIBUTING.
- `python main.py sync` : lance chaque source configurée dans un sous-processus isolé (délai, code de retour agrégé), journal JSON dans `data/logs/sync.log`, statut par source (`sync_checkpoints`, `logs_systeme`) affiché dans *Système → Synchronisation* (migration 005).
- `scripts/backup_db.py` et timer systemd `dynastasie-backup` : sauvegarde quotidienne rotative de la base ; documentation de restauration.

- Registre de piliers (`src/pillars/`) : navigation, commandes CLI (`python main.py --help`) et sources de synchronisation en dérivent ; ajouter un pilier ne touche plus `main.py` (voir `docs/piliers.md`).
- Couches `src/repositories/` (SQL) et `src/services/` (règles métier), avec leurs tests (+60 tests, couverture 64 %).

### Modifié
- `scripts/sync_conteneur.sh` : le conteneur synchronise sans `logos` (`sync --skip`, ou `DYNASTASIS_SYNC_SKIP`), `logos` tourne sur l'hôte où l'ADB retrouve le téléphone par mDNS ; `SAMSUNG_ADB_MDNS=1` remplace l'IP fixe.
- Les vues `resonance`, `vigueur` et `forge` sont découpées en paquets (un module par onglet) ; le SQL et les calculs en sortent. Aucun changement visuel.
- `python main.py sync` ignore les sources des piliers désactivés dans `[piliers] actifs`.
- Seuil de couverture de la CI : 7 % → 60 %.
- `core/projets.py` et `core/system_engine.py` deviennent `services/projets.py` et `services/semaines.py`.
- Le timer systemd lance `main.py sync` (toutes les sources) via `scripts/sync_conteneur.sh`, qui ne fait pas échouer l'unité quand le conteneur est arrêté.
- Les deux modes deviennent des codes configurables (migration 004 : levée des contraintes `CHECK`, conversion des anciennes valeurs vers les codes de la configuration).
- Le critère propre à l'auteur devient le critère générique « engagement » : tag `FORGE_ENGAGEMENT`, colonnes `focus_engagement_min`, `jours_engagement_semaine`, `forge_drill_engagement`, `plan_drill_engagement`, `forge_jours_engagement_mois` (migration 004).
- Les seuils du score ne sont plus codés dans les vues SQL : ils viennent de `score_config` / `modes_config`.
- `docker-compose.yml` : le fichier de secrets est facultatif ; `./config` est monté en lecture seule.
- `today_paris` / `now_paris` deviennent `today_local` / `now_local` (fuseau configurable).

### Corrigé
- `python main.py logos` (et la synchro) signale clairement l'échec d'ADB : message `[ÉCHEC ADB]` et code de retour 1, au lieu d'un « ok » qui réutilisait le cache sans le dire.
- ADB : le téléphone jumelé est d'abord retrouvé par mDNS (indépendant du réseau), l'IP `SAMSUNG_ADB_HOST` n'est plus qu'un repli et devient facultative en local.
- Petits graphiques 7 j de Vigueur : étiquettes « jj/mm » en axe catégoriel (elles s'affichaient « Mar 2010 »).

### Supprimé
- Widget audio externe de la barre latérale (réactivable via `[interface] widget_url`).

## Avant la mise en public

- Secrets hors dépôt (`secrets.env`), lockfile `pip-compile`, Dependabot, CI GitHub Actions, Python 3.12.
- Contenu personnel déplacé en base (`profil_contenu`), historique git assaini.
- Migrations numérotées (`PRAGMA user_version`), tests du scoring, du gel hebdomadaire, des habitudes et du focus, couverture dans la CI.
- Onglet « Projets en cours » (projets, phases, tâches).
