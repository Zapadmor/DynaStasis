# DynaStasie — DynaStasis

Interface de suivi hebdomadaire : sport (Intervals.icu / Strava), temps d'écran (Samsung ADB), finances, habitudes.

---

## Prérequis

```bash
source env/bin/activate
```

La DB principale est dans `db/dynastasie.db`.

---

## Schéma et migrations

`db/schema.sql` est le schéma de base (base vide). Les évolutions passent par des migrations numérotées `db/migrations/NNN_description.sql`, appliquées dans l'ordre au lancement de l'app ou par :

```bash
python main.py init-db
```

La version appliquée est stockée dans `PRAGMA user_version`. Pour ajouter une évolution : créer le fichier suivant (`004_...sql`), sans modifier les migrations déjà publiées. Les `ALTER TABLE ... ADD COLUMN` déjà appliqués sont ignorés, donc une migration peut être rejouée sans erreur.

---

## Explorer la base de données — sqlite_web

Lance une interface web locale pour inspecter toutes les tables SQLite :

```bash
sqlite_web db/dynastasie.db --port 8080
```

Puis ouvre [http://localhost:8080](http://localhost:8080).

Tables utiles à explorer :
- `semaines_audit` — hub central, une ligne par semaine ISO
- `vigueur_entries` — CTL / ATL / TSB / HRV / RHR / sommeil / steps par jour
- `screen_sessions` — sessions d'apps Samsung brutes
- `sync_checkpoints` — horodatage du dernier sync par source

---

## Bot Vigueur — Intervals.icu + Strava → SQLite

Récupère les métriques sport (CTL, ATL, TSB, HRV, RHR, sommeil, steps, activités) depuis Intervals.icu, et les records personnels Strava.

### Sync quotidien (mode incrémental)

```bash
python main.py vigueur
```

En mode incrémental, le bot ne récupère que depuis le dernier `date_entry` connu en base — rapide, idéal pour l'automatisation quotidienne.

Le résumé affiché couvre toutes les métriques de la dernière entrée :
```
Intervals.icu — 2026-06-19
  Forme     CTL=62.0  ATL=58.5  TSB=3  (Δ7j +2.1)
  Santé     VO2max=55.2  HRV=72.1  RHR=48.0
  Récup     Sommeil=452 min  Pas=9843
  Sport     TSS=85.0  Distance=12.3 km  Durée=68.5 min
```

### Rattrapage après une absence — mode full

Quand tu n'as pas été sur le PC plusieurs jours ou semaines et que la base a du retard :

```bash
# Rattraper les 180 derniers jours (défaut)
python main.py vigueur --full

# Rattraper une période plus longue (ex : 365 jours)
python main.py vigueur --full --lookback 365
```

`--full` désactive le mode incrémental : le bot ignore le dernier checkpoint et fetche toute la fenêtre `--lookback` depuis Intervals.icu.
`--lookback N` contrôle le nombre de jours d'historique (défaut : 180). Augmente-le si tu reviens d'une longue absence.

### Options complètes

| Option | Effet |
|--------|-------|
| `--full` | Désactive le mode incrémental, full sync sur `--lookback` jours |
| `--lookback N` | Jours d'historique (défaut : 180, ignoré sans `--full`) |

---

## Bot Logos — Temps écran Samsung ADB → SQLite

Récupère les sessions d'utilisation d'apps depuis le Samsung via ADB WiFi, stocke dans SQLite.

### Usage standard

```bash
python main.py logos
```

Le Samsung doit être connecté au même réseau. L'IP ADB est lue depuis la variable `SAMSUNG_ADB_HOST` (voir `secrets.env.example`).

### Saisie manuelle — audit hebdomadaire

Quand les sessions ADB sont incomplètes ou que l'audit est fait sans le téléphone :

```bash
python main.py logos --manual
```

Saisie interactive :
```
── Saisie manuelle du temps d'écran ──
Temps d'écran total (minutes) : 312
Top apps (ex: YouTube 120, Instagram 45) [Entrée pour passer] : YouTube 140, Snapchat 85, Chrome 50
```

Écrit directement dans `semaines_audit.screen_time_min` et `semaines_audit.top_apps_text` pour la semaine en cours, puis relance la cascade de rollups.

### Options complètes

| Option | Effet |
|--------|-------|
| `--manual` | Saisie manuelle sans ADB (pour l'audit hebdomadaire) |
| `--host IP` | IP du Samsung (remplace `SAMSUNG_ADB_HOST`) |
| `--top-n N` | Nombre d'apps à afficher dans le résumé (défaut : 5) |

---

## Projets en cours

L'onglet **Forge → Projets en cours** suit des projets découpés en **phases** ordonnées, chacune avec des **tâches à cocher** (cases persistées en base). Pour chaque projet au statut `en_cours`, il affiche :

- le titre, la description et la progression globale (tâches cochées / total) ;
- la **phase courante** : la première phase, dans l'ordre chronologique, qui compte encore au moins une tâche non cochée ; avec son objectif, ses cases, sa prochaine étape et ses notes ;
- la liste de toutes les phases (✓ terminée · ▸ courante · ○ à venir).

Quand toutes les cases sont cochées, un bouton propose de marquer le projet comme terminé. Le bloc **« + Gérer les projets »** permet de créer un projet, d'ajouter des phases et des tâches, et de changer un statut (`en_cours`, `en_pause`, `termine`, `abandonne`).

Tables : `projets`, `projet_phases`, `projet_taches` (voir `db/schema.sql`) ; logique dans `src/core/projets.py`.

---

## Contenu personnel

Aucun texte personnel (plan de carrière, objectifs, phases d'entraînement…) n'est stocké dans le code : il vit dans la base SQLite (`db/dynastasie.db`, ignorée par git et exclue des images Docker), table `profil_contenu`. Les écrans affichent un message vide tant que la clé correspondante n'est pas renseignée.

```bash
python main.py profile export mon_profil.json   # sauvegarde
python main.py profile import mon_profil.json   # chargement / restauration
```

Clés utilisées : `logos.plan_carriere`, `logos.cursus_titre`, `vigueur.macro_cycle`, `vigueur.objectif_course`, `vigueur.vo2max_actuel`, `forge.objectif_pro_titre`, `audit.*`. Les applis comptées comme « distractives » se règlent dans la table `apps_distrayantes`.

---

## Tests

```bash
pytest -q                 # suite complète (bases SQLite temporaires)
pytest -q --cov           # avec couverture de src/ (seuil minimal dans pyproject.toml)
```

---

## Interface Streamlit

```bash
python main.py app
# ou directement :
streamlit run src/app/ui_main.py
```

Accès : [http://localhost:8501](http://localhost:8501)

---

## Récap commandes fréquentes

```bash
# Exploration DB
sqlite_web db/dynastasie.db --port 8080

# Sync sport — quotidien
python main.py vigueur

# Sync sport — rattrapage après absence
python main.py vigueur --full --lookback 365

# Sync temps écran (depuis ADB)
python main.py logos

# Saisie manuelle temps d'écran (audit hebdomadaire)
python main.py logos --manual

# Interface web
python main.py app
```
