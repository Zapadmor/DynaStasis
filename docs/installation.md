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
