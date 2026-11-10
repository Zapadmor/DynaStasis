# Journal des changements

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Pas encore de versions numérotées : les changements sont regroupés par période.

## Non publié

### Ajouté
- Bascule entre machines fiabilisée (`scripts/handoff.py bascule`, appelé par `stop_peer.sh` et le bouton « Basculer ici »). Streamlit **et** l'API sont désormais arrêtés/démarrés ensemble (`DYNASTASIS_CONTAINERS`) ; avant tout démarrage local : synchro Syncthing vérifiée par l'API (scan forcé, pair à 100 %), sha256 de la base identique des deux côtés, `integrity_check`, aucun `-wal` résiduel, aucun nouveau `sync-conflict`. Le même contrôle protège le démarrage et l'extinction (une base non saine n'est jamais propagée). Cause traitée : corruptions « malformed » à chaque arrêt/allumage d'un PC (fichier remplacé par Syncthing sous un conteneur ouvert ou à côté d'un `-wal` périmé ; étape hôte du timer `dynastasie-sync` qui écrivait dans la base d'un PC non actif).
- Temps d'écran ADB : quand le téléphone n'annonce pas son service mDNS, repli par balayage des ports 30000-50000 de l'hôte configuré (`SAMSUNG_ADB_HOST`) puis `adb connect`, avant l'ancien repli sur le port 5555 (inexistant avec le débogage sans fil d'Android 11+). Le port de jumelage est déconnecté s'il ne donne pas d'appareil.
- Bouton *Sync Écran* fiabilisé : en conteneur, demande déposée dans `data/` et traitée sur l'hôte par `dynastasie-logos.path` (`scripts/handle_logos_request.sh`), car le mDNS ne passe pas le réseau pont ; sinon sous-processus avec délai. Un échec ADB n'est plus affiché comme un succès, et la synchro alimente `sync_checkpoints` et `logs_systeme`. Correctif : `logs_systeme.timestamp` est écrit à l'heure locale configurée (il était en UTC dans le conteneur, 1 h de retard).
- Vigueur : onglet Charge & Récupération réduit à la courbe CTL/ATL/TSB (pauses du système en bandes ambre) et au macro-cycle avec ses jalons cochables, tâches de l'objectif Forge désigné par `vigueur.macro_cycle_objectif`. Onglet Performances, mode téléphone, flux de séance en direct, 5 métriques, 4 mini-graphiques et temps d'écran supprimés. Log Workouts : saisie après coup avec les fonctions de la PWA (templates, exercices statiques et lestés, EMOM avec temps par minute, côté D/G, séries vides ignorées, numéro et volume à l'enregistrement) ; édition d'une séance en conservant son identifiant. Migration 012 (`workout_session_sets.side`), migration 013 (index des séances : la requête « Préc. » passe de 38 s à quelques millisecondes). Compteur d'entraînements : les activités Intervals.icu comptent après la date de départ.
- PWA de séance mobile (`src/api/`, service `api` de docker-compose) : API FastAPI protégée par jeton (`DYNASTASIS_API_TOKEN`), `POST /api/workouts` atomique et idempotent, `GET /api/history`, `GET /api/exercises` (colonne « Précédent »), page installable avec brouillon hors ligne. Migration 008 : `workout_sessions.client_uuid`, `workout_session_sets.rpe`. Nouveau type de série `D` (drop). `GET /api/templates` : démarrage d'une séance depuis un template, exercices choisis dans la bibliothèque ; un exercice inconnu est refusé sauf création explicite. Réglages poids du corps (enregistré par séance, repris de la dernière séance si vide) et taille. Saisie rapide : « Préc. » copiable, barre − / + sans clavier, colonne « Lest » pour les exercices au poids du corps (formule choisie à la création), exercices statiques en secondes (`exercise_library.unit`). EMOM d'une minute par série : bloc multi-exercices personnalisé (durée totale multiple du nombre d'exercices) ou issu d'un template, barre de temps par ligne, temps mis pour faire les reps (`workout_session_sets.duration_s`), bips aux secondes 57-58-59 puis bip différent à 60. Interface sobre sans pictogrammes, menus déroulants. Migration 009. Séries validées stockées mais masquées (résumé + « Voir »), retrait des séries non validées, envoi des seules séries validées, fenêtre de fin « Entraînement #X / Volume Y kg » (`number` et `volume_kg` dans la réponse de `POST /api/workouts`). Migration 011 et `python main.py training-counter` : numéro d'entraînement aligné sur un compteur externe (point de départ local), synchro Intervals.icu enregistrant chaque activité (`intervals_activities`). Migration 010 : `exercise_library.bw_fraction` (0.7 pour les pompes) et `rep_factor` (1.0) dans le volume ; `scripts/suggest_rep_factor.py` propose un coefficient sur les données de l'utilisateur. Correctif : « Préc. » ignore les séances sans série validée. Temps d'entraînement au journal : `workout_sessions.duration_min` et `vigueur_entries.workout_min` (non écrasée par Intervals.icu), pris en compte par le score et le graphique d'entraînement.
- `scripts/handoff.py` et service systemd `dynastasie-handoff` : à l'extinction, arrêt du conteneur local, attente de la synchronisation Syncthing puis démarrage sur l'autre machine ; au démarrage, lancement local seulement si l'autre machine est joignable, arrêtée et synchronisée, sinon attente de confirmation (notification à l'ouverture de session). Installé par `scripts/systemd/install.sh`.
- Migration 007 : suppression de la table historique `cours_utc` (contenu déjà copié dans `cours_ecole`).
- `python main.py documents import|export|list` et table `documents` (migration 006) : notes et rapports markdown stockés dans la base, hors historique git.
- Résonnance → Notes pour trop tard → « Chantiers & RETEX » : chantiers d'introspection (RETEX, chantier psy, exercice, écueil, défi relationnel, qualité, défaut), rattachés à une personne ou à soi, avec statut et entrées de suivi datées (tables `npt_chantiers`, `npt_chantier_entrees`).
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
