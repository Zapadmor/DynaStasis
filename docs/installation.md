# Installation

DynaStasis tourne en local : une application Streamlit et une base SQLite. Deux façons de l'installer ; les deux acceptent la [base de démonstration](#base-de-démonstration).

## Prérequis

| | Docker | Local |
|---|---|---|
| Outils | Docker + Compose v2.24 ou plus | Python 3.12 |
| Système | Linux, macOS, Windows (WSL) | idem |
| Réseau | uniquement pour télécharger l'image | aucun, hors synchronisations |

## Base de démonstration

`python main.py seed-demo` charge des données **fictives** (12 semaines d'habitudes, de focus, de sport, de temps d'écran, de finances, des objectifs, un projet à phases, un plan de carrière d'exemple). Les dates sont relatives à aujourd'hui et le jeu est déterministe.

- Cible par défaut : `data/demo/dynastasie-demo.db` ; `--db chemin` ou `DYNASTASIS_DB` pour une autre.
- **Idempotent** : relancer la commande recrée la base de démo.
- **Garde-fous** : la commande refuse d'écraser `db/dynastasie.db` (sauf `--base-reelle`) et toute base qui contient d'autres données.

## Docker

### Démonstration

```bash
docker compose -f docker-compose.demo.yml up --build   # http://localhost:8502
```

### Image publiée

`docker pull ghcr.io/zapadmor/dynastasis-app:latest` (ou `:vX.Y.Z`, `:sha-xxxxxxx`, `:latest-adb` pour la variante avec `adb`) ; amd64 et arm64. Le dépôt reste nécessaire pour utiliser `docker-compose.yml` (configuration, volumes) : l'image seule suffit pour la démo (voir le README).

### Vos données

```bash
docker compose up -d --build                            # http://localhost:8501
```

- La base vit dans `./db/` (créée au premier lancement), les fichiers d'import dans `./data/`.
- Les secrets sont lus dans `~/.config/dynastasie/secrets.env` (variable `DYNASTASIS_ENV_FILE` pour un autre chemin) ; le fichier est **facultatif**.
- `./config/` est monté en lecture seule : `config/user.toml` y est lu.
- Si votre utilisateur n'a pas l'UID 1000 : `DYNASTASIS_UID=$(id -u) DYNASTASIS_GID=$(id -g) docker compose up -d`.
- Pour voir la démo dans ce conteneur-là (base vide au départ) : `docker compose run --rm streamlit python main.py seed-demo --db /app/dbdata/dynastasie.db` avant `up`. La commande refuse d'écraser une base qui contient déjà vos données.
- `adb` (temps d'écran Android) n'est pas dans l'image par défaut : `DYNASTASIS_TARGET=adb docker compose up -d --build` construit la variante qui l'inclut (voir [configuration](configuration.md#temps-décran-android-adb)). Variable à placer dans `.env` pour la conserver.
- Réglages (UID/GID, DNS, fichier de secrets, cible `adb`, limites mémoire/CPU) : copiez `.env.example` vers `.env`. Le conteneur redémarre seul (`restart: unless-stopped`) et expose un `healthcheck` visible dans `docker compose ps`.
- Mise à jour : `git pull && docker compose up -d --build`. Les migrations de base s'appliquent au démarrage.

## Local

```bash
python3 -m venv env && source env/bin/activate
pip install -r requirements.txt            # versions figées (lockfile)
python main.py init-db                     # crée db/dynastasie.db
python main.py app                         # http://localhost:8501
```

Pour les outils de développement : `pip install -r requirements-dev.txt` (voir [CONTRIBUTING](../CONTRIBUTING.md)).

## Synchronisation et logs

`python main.py sync` lance chaque source configurée (Intervals.icu, Strava, ADB, exports bancaires) dans un processus à part, avec un délai maximal : **une source en échec n'empêche pas les autres**. Le code de retour vaut 1 si l'une a échoué, 0 sinon (y compris quand aucune source n'est configurée). `--only intervals,strava` limite les sources, `--timeout N` fixe le délai (secondes).

- Journal structuré (une ligne JSON par évènement) sur la sortie standard et dans `data/logs/sync.log` (rotation 1 Mo × 3).
- Statut par source (dernière réussite, dernière erreur, durée) : page *Système → Synchronisation*, tables `sync_checkpoints` et `logs_systeme`.

## Sauvegarde et restauration

La base est un seul fichier SQLite. Pour une copie manuelle cohérente : `python3 scripts/backup_db.py` (copie rotative vérifiée dans `~/.local/share/dynastasie/db-backups/`, 14 conservées ; `--db`, `--dest`, `--keep` pour changer). Le contenu de profil (textes, plans) s'exporte aussi : `python main.py profile export profil.json`.

**Restaurer** :

```bash
docker compose stop streamlit                       # ou arrêtez l'application locale
mv db/dynastasie.db db/dynastasie.db.avant-restauration
rm -f db/dynastasie.db-wal db/dynastasie.db-shm    # fichiers annexes de l'ancienne base
cp ~/.local/share/dynastasie/db-backups/dynastasie-AAAAMMJJ-HHMMSS.db db/dynastasie.db
docker compose start streamlit                      # les migrations manquantes s'appliquent au démarrage
```

## Saisie mobile (PWA de séance)

Une page web installable (`src/api/static/`) servie par l'API FastAPI (`src/api/`) permet de saisir une séance depuis le téléphone et de l'écrire dans les tables `workout_*` de la base, visibles ensuite dans Vigueur → Historique. Le brouillon reste dans le navigateur (`localStorage`) ; à la fin, la séance part vers l'API, ou reste en file avec un bouton « Réessayer » si le réseau échoue. Chaque séance porte un `client_uuid` : un renvoi ne crée pas de doublon.

1. **Jeton** : ajoutez `DYNASTASIS_API_TOKEN=<valeur longue aléatoire>` dans `~/.config/dynastasie/secrets.env`. Sans lui, l'API refuse toute requête (503).
2. **Lancement** (base déjà migrée : démarrez d'abord `streamlit`, ou `python main.py init-db`) :
   ```bash
   docker compose up -d api        # écoute sur le port 8000
   ```
3. **Adresse du PC** : `tailscale ip -4` (adresse en `100.x.y.z`) ou le nom MagicDNS du PC dans `tailscale status`.
4. **Sur le téléphone** (Tailscale actif) : ouvrez `http://100.x.y.z:8000` dans Chrome, déroulez *Réglages*, laissez l'URL vide (la page utilise sa propre adresse) et collez le jeton.
5. **Installation** : menu ⋮ de Chrome → « Ajouter à l'écran d'accueil ». En HTTP simple, Chrome crée un raccourci ; le mode « application installée » et le cache hors ligne de la page exigent HTTPS. Pour l'obtenir : `tailscale serve --bg 8000` (HTTPS activé dans la console d'administration Tailscale), puis ouvrez l'adresse `https://<machine>.<tailnet>.ts.net`. Ce point n'a pas été vérifié sur un téléphone précis.

**Un seul écrivain.** Si deux PC partagent `db/` via Syncthing, l'API ne doit tourner que sur le PC dont la base est active : `docker compose stop api` sur l'autre. L'URL du téléphone doit viser ce PC.

**Templates et exercices.** Au démarrage d'une séance vide, la page propose tes templates (`workout_templates`) : un toucher pré-remplit les exercices et leurs séries prévues. Les exercices s'ajoutent depuis la bibliothèque (liste filtrable) ; un nom absent de la bibliothèque (comparaison insensible à la casse) est **refusé par le serveur** (422), sauf création explicite via « Créer le nouvel exercice », pour qu'une faute de frappe ne crée plus de doublon. Un exercice de template dont la ligne de bibliothèque a disparu est ignoré. Les templates se modifient dans Streamlit, pas depuis la page.

**Poids du corps et taille** (Réglages de la page) : le poids est enregistré avec chaque séance (`workout_sessions.bodyweight_kg`) et sert au calcul de la charge des exercices `bw_plus_weight` (tractions, dips : la colonne « Kg » est alors le lest). S'il est vide, la page reprend le dernier poids enregistré. La taille est conservée dans le navigateur uniquement : aucune table ne la stocke pour l'instant.

**Saisie rapide.** « Préc. » est cliquable : un toucher copie kg et reps de la dernière séance (avec, en EMOM, le temps mis la fois précédente). Toucher un champ kg/reps/RPE affiche une barre − / + (pas de 2,5 kg, 1 rep, 0,5 RPE ; 5 ou 10 s pour un exercice statique) sans ouvrir le clavier ; « Clav. » bascule vers le clavier numérique (choix mémorisé). Pour les exercices au poids du corps (`bw_plus_weight`) la colonne devient « Lest », pour un exercice statique (`unit = 'sec'`) « Sec ».

**Menus.** Le template se choisit dans un menu déroulant (« Charger »), les exercices dans une liste groupée par catégorie ; « + Nouvel exercice... » demande le nom et le type : charge, corps + lest, ou statique (secondes tenues).

**EMOM.** Un EMOM dure toujours une minute par série. Chaque bloc a un en-tête collant (minute en cours, temps restant, Start / Pause / Reset) et **une barre de temps sur chaque ligne** : valider la série (OK) pendant sa propre minute enregistre le temps mis pour faire les reps prévues (`workout_session_sets.duration_s`), indicateur de forme comparé au « Préc. » de la séance suivante. Alertes sonores et vibration : un bip aux secondes 57, 58 et 59, puis un bip différent à 60 (début de la minute suivante) ; double bip long à la fin. Les séries ne sont jamais cochées automatiquement. Un exercice de template avec `emom_interval_sec` donne un bloc d'un exercice ; « Nouvel EMOM » crée un bloc personnalisé : tu choisis les exercices (chacun a sa minute à tour de rôle) et la durée totale, qui doit être un multiple du nombre d'exercices (10 min avec 2 ou 5 exercices, 9 ou 12 avec 3...). Le temps est calculé sur l'horloge réelle : le minuteur survit à un rechargement de la page. L'écran n'est maintenu allumé que sous HTTPS (Wake Lock) : en HTTP, règle la mise en veille d'Android au maximum, sinon le son et la vibration s'arrêtent écran éteint.

**Saisie après coup (Streamlit, onglet Vigueur → Log Workouts).** Quand tu oublies la PWA, le formulaire enregistre la séance par le même chemin que l'API (`import_session`) : volume, coefficients, durée, journal quotidien et numéro d'entraînement sont identiques. Renseigne date, heure de début, durée (minutes ; 0 = non renseignée, rien n'est ajouté au journal) et poids du corps (dernier poids connu par défaut), puis charge un template ou ajoute des exercices (menu groupé par catégorie, « Nouvel exercice » : charge, corps + lest ou statique). Chaque exercice est un tableau éditable (type, côté D/G, charge ou lest, reps ou secondes, RPE, « Préc. ») ; les lignes sans répétitions sont ignorées et « Retirer les séries vides » les supprime. « Nouvel EMOM » crée un bloc d'exercices à tour de rôle (durée multiple du nombre d'exercices) avec une colonne « Temps (s) » à saisir. « Mod » dans l'historique recharge une séance dans le même formulaire et la remplace **en gardant son identifiant** (le rattachement Intervals.icu et le rang dans le compteur sont conservés).

**Macro-cycle et jalons.** L'onglet Charge & Récupération se limite à la courbe de charge, où les périodes de gel du système (`system_freezes`) sont tracées en bandes ambre avec leur raison, et au macro-cycle. Les phases sont le contenu de profil `vigueur.macro_cycle` ; les jalons sont les tâches de l'objectif Forge désigné par la clé de profil `vigueur.macro_cycle_objectif` (id de l'objectif), rangées dans la phase qui contient leur échéance. La case d'un jalon le valide, exactement comme dans l'onglet Objectifs de la Forge (même table `taches`).

**Côté D/G et exercices unilatéraux.** `workout_session_sets.side` (`'D'`/`'G'`) enregistre le bras d'une série (grips, un bras) ; « Préc. » compare chaque côté à la même série du même côté. Les secondes d'un exercice statique acceptent des décimales (11,4 s). Un maintien isométrique de charge maximale se règle avec `rep_factor = 0` pour rester hors du volume.

**Séries validées et séries vides.** Une série validée (OK) est stockée mais n'est plus affichée : un résumé (« Validées 2/8 », avec en EMOM le temps de la dernière série et le temps moyen) la remplace, et « Voir » la ré-affiche pour la corriger. « Retirer les séries non validées » (par exercice ou par EMOM) supprime les séries surdimensionnées ; un exercice sans série validée disparaît. À l'envoi, seules les séries validées sont enregistrées : la confirmation indique combien de séries non validées sont ignorées.

**Compteur d'entraînements.** `python main.py training-counter` affiche l'état ; `python main.py training-counter set COUNT --first-session ID [--date AAAA-MM-JJ]` fixe le point de départ (COUNT = valeur du compteur externe avant le premier entraînement compté ; ID = première séance saisie comptée ; date = les activités Intervals.icu comptées sont celles d'un jour **strictement postérieur** (celles du jour de départ sont déjà dans le compteur externe), défaut aujourd'hui). La valeur reste dans ta base locale, jamais dans le dépôt. La synchro enregistre désormais chaque activité Intervals.icu (table `intervals_activities`, une ligne par activité, tous types confondus) ; une activité rattachée à une séance via `workout_sessions.intervals_activity_id` n'est comptée qu'une fois. Le numéro est le rang chronologique : une activité plus ancienne synchronisée plus tard décale les numéros suivants. **Limite connue : tant que séance PWA et activité Intervals.icu d'un même entraînement ne sont pas rattachées, elles comptent pour deux.**

**Coefficients du volume.** `exercise_library.bw_fraction` est la part du poids du corps réellement soulevée pour les exercices `bw_plus_weight` (0.7 pour les pompes d'après Suprak et al. 2011 ; le lest s'ajoute en entier ; 1.0 ailleurs). `exercise_library.rep_factor` convertit les reps d'un mouvement complexe (muscle-up, grips) dans le volume : 1.0 par défaut, car aucune source scientifique de conversion n'a été trouvée. Ces coefficients n'agissent que sur les séances enregistrées après la migration 010 et uniquement via la PWA (l'onglet Log Workouts de Streamlit compte toujours 100 % du poids du corps) ; `rep_factor` ne modifie pas `load_kg`. Pour estimer un coefficient sur tes propres données : `python3 scripts/suggest_rep_factor.py --target "Muscle Up" --reference "Pull Up"` (lecture seule ; refuse sous 5 séances par exercice ; n'applique rien).

**Fin de séance.** Après la synchronisation, une fenêtre affiche « Entraînement #X » et « Volume Y kg ». X est le numéro d'entraînement, aligné sur un compteur externe (Strava) : point de départ saisi une fois en local, puis +1 par séance saisie (au moins une série validée) et par activité Intervals.icu. Sans point de départ configuré, X est le rang de la séance dans l'historique de la base. Y est la somme, sur les séries validées, de (poids du corps + lest) × reps, c'est-à-dire `workout_sessions.session_volume_kg` ; les exercices statiques (en secondes) n'y comptent pas.

**Temps d'entraînement au journal quotidien.** La durée d'une séance va de la première action (Start d'un EMOM ou première série validée) à la dernière série validée ou fin d'EMOM ; elle est enregistrée dans `workout_sessions.duration_min`. La somme du jour est recopiée dans `vigueur_entries.workout_min`, colonne que la synchro Intervals.icu n'écrase pas (elle écrase `moving_time_min`). Le score hebdomadaire, le journal et le graphique « Entraînement (min) » additionnent `moving_time_min + workout_min` ; l'allure (min/km) et `v_vigueur_hebdo` restent calculées sur les minutes Intervals.icu seules. **Limite connue : tant que la séance PWA n'est pas rattachée à la courbe de fréquence cardiaque correspondante (`workout_sessions.intervals_activity_id`), une séance présente à la fois dans Intervals.icu et dans la PWA est comptée deux fois.**

Types de série (touche sur le numéro de série) : série de travail (numérotée), `W` échauffement, `D` drop, `F` échec. Un exercice inconnu est ajouté à la bibliothèque (`exercise_library`) avec la formule de charge `weight`.

## Planification (Linux, facultatif)

`scripts/systemd/install.sh` installe deux timers systemd :

| Timer | Fréquence | Action |
|---|---|---|
| `dynastasie-sync` | 01h, 07h, 13h, 19h | `docker exec dynastasie-streamlit python main.py sync --skip logos`, puis `python main.py sync --only logos` sur l'hôte (via `scripts/sync_conteneur.sh` : conteneur arrêté → journalisé, sans échec ; l'étape hôte demande le venv `env/`) |
| `dynastasie-backup` | tous les jours à 03h30 | `scripts/backup_db.py --keep 14` |

```bash
sudo bash scripts/systemd/install.sh      # sudo : écrit dans /etc/systemd/system ; relancer après une mise à jour du dépôt
sudo bash scripts/systemd/uninstall.sh
journalctl -u dynastasie-sync -u dynastasie-backup --since today    # journaux
systemctl list-timers 'dynastasie-*'
```

## Dépannage

| Symptôme | Piste |
|---|---|
| `env file ... not found` | Compose trop ancien : utilisez la v2.24+ (le fichier de secrets est facultatif) |
| Page vide / « Aucune semaine active » | normal sur base vide : saisissez une habitude ou lancez `seed-demo` |
| `database is locked` | une autre instance écrit en même temps ; fermez-la |
| Accès refusé dans `db/` ou `data/` avec Docker | ajustez `DYNASTASIS_UID` / `DYNASTASIS_GID` |

Autres questions : [FAQ](faq.md).
