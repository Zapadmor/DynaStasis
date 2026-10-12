# Architecture

## Vue d'ensemble

```
 sources (facultatives)            base locale                    interface
┌────────────────────┐        ┌──────────────────┐        ┌──────────────────────┐
│ Intervals.icu      │ bots/  │                  │        │ Streamlit            │
│ Strava             ├───────▶│  SQLite          │◀───────┤ src/app/ui_main.py   │
│ ADB (Android)      │ src/   │  db/dynastasie.db│  vues  │ src/app/views/*      │
│ exports bancaires  │collect.│                  │  SQL   │                      │
└────────────────────┘        │  schema.sql      │        └──────────▲───────────┘
 saisie manuelle ─────────────▶  + migrations    │                   │ lit
 (interface, CLI)             └────────▲─────────┘        config/user.toml
                                       │                  secrets.env (hors dépôt)
                              src/core/ (règles : cascade, focus, habitudes, projets)
```

| Dossier | Contenu |
|---|---|
| `main.py` | orchestrateur CLI |
| `bots/` | scripts de synchronisation (`vigueur`, `logos`) |
| `src/core/sync_runner.py` | orchestre les sources (`main.py sync`) : un sous-processus par source, délai, statut en base, journal JSON |
| `src/collectors/` | clients Intervals.icu, Strava, ADB, finance, journal de séances |
| `src/pillars/` | registre des piliers : navigation, commandes CLI et sources de synchronisation (un module par pilier) |
| `src/repositories/` | accès aux données : SQL pur (`projets`, `semaines`) |
| `src/services/` | règles métier au-dessus des repositories (`projets`, `semaines` : semaine ISO, gel, cascade) |
| `src/core/` | `focus_manager`, `habit_manager`, `profile`, `user_config`, `tz`, `demo`, `sync_runner` (en cours de migration vers `services/`) |
| `src/app/` | interface : `ui_main.py` (navigation), `components.py` (barre latérale, thème), `views/` (une page par pilier) |
| `src/database/connection.py` | connexion, migrations, `db_session()` |
| `db/` | `schema.sql` (schéma de base), `migrations/` |
| `config/` | `user.toml.example` |

## Couches

```
 src/app/views/*  ──▶  src/services/*  ──▶  src/repositories/*  ──▶  SQLite
 (rendu Streamlit)     (règles métier)       (SQL pur)
```

| Couche | Rôle | Interdit |
|---|---|---|
| **repository** (`src/repositories/<domaine>.py`) | une fonction = une requête ; reçoit la connexion `conn` en premier argument, renvoie des `dict`, des listes de `dict` ou des types simples | Streamlit, règles métier, ouverture de connexion, `commit` |
| **service** (`src/services/<domaine>.py`) | règles de gestion (calculs, validations, enchaînements) ; ouvre la transaction (`db_session()`) et appelle les repositories ; les calculs purs sont des fonctions séparées, testables sans base | Streamlit, SQL |
| **vue** (`src/app/views/`) | rendu et saisie ; appelle les services | SQL, règles métier |

Les tests d'un repository utilisent la fixture `conn` (base temporaire migrée) ; ceux d'un service testent d'abord les fonctions pures, puis le cas complet avec la fixture `db`. Les vues restent couvertes par les `AppTest` de `tests/test_pages.py`. Le code historique migre vers ce schéma pilier par pilier ; `projets` et `semaines` en sont les modèles.

## Flux de données

1. Une source (bot ou saisie) écrit dans une table à grain **jour** : `vigueur_entries`, `habitude_logs`, `focus_sessions`, `screen_sessions`.
2. `get_or_create_week_id(date)` retrouve ou crée la ligne de la semaine ISO dans `semaines_audit` (clé naturelle : `week_start`, le lundi). Elle y fixe le mode (`sequences_mode`) et le drapeau de gel (`system_freezes`).
3. **Cascade** (`trigger_cascade_week`) : recalcule les cumuls de la semaine (focus, habitudes, engagement, projets de fond) dans `semaines_audit`, puis le score depuis la vue `v_score_semaine`.
4. Les vues lisent les seuils dans `score_config` et `modes_config`, recopiées depuis `config/user.toml` à chaque initialisation de la base.
5. L'interface lit principalement les vues (`v_score_semaine`, `v_progression_quotidienne`, `v_vigueur_hebdo`, `v_habitudes_hebdo`, `v_net_worth_actuel`).

## Schéma de données

`semaines_audit` est le **hub** : une ligne par semaine.

| Groupe | Tables |
|---|---|
| Hub | `semaines_audit`, `logs_systeme`, `system_freezes`, `sequences_mode`, `sync_checkpoints` |
| Quotidien | `habitude_logs`, `focus_sessions`, `vigueur_entries`, `screen_sessions`, `apps_distrayantes` |
| Sport | `plan_entrainement`, `workout_*`, `exercise_library`, `vigueur_personal_records`, `vigueur_predictions_logs`, `strava_oauth_tokens` |
| Finance | `comptes`, `soldes_comptes`, `transactions`, `positions_investissement`, `budgets_mensuels`, `revenus_budget`, `depenses_budget` |
| Objectifs et projets | `objectifs`, `taches`, `projets`, `projet_phases`, `projet_taches` |
| Académique | `cours_ecole` (catalogue et historique de cours, nom historique), `logos_gpa` |
| Réflexion | `audit_narrative` (hebdo), `audit_trimestriel`, `audit_annuel`, `npt_personnes`, `npt_notes` |
| Configuration | `profil_contenu` (textes de profil), `score_config`, `modes_config` |
| Vues | `v_score_semaine`, `v_progression_quotidienne`, `v_deep_focus_hebdo`, `v_vigueur_hebdo`, `v_habitudes_hebdo`, `v_net_worth_actuel`, `v_score_params` |

## Migrations

`db/schema.sql` est le schéma de **base** (état initial). Les évolutions sont des fichiers numérotés `db/migrations/NNN_description.sql` (ou `.py` exposant `apply(conn)` quand le SQL ne suffit pas, par exemple pour reconstruire une table). `PRAGMA user_version` mémorise le dernier numéro appliqué ; au démarrage (`init_db()`) :

1. `schema.sql` est exécuté (créations `IF NOT EXISTS`) ;
2. les migrations en attente s'appliquent dans l'ordre, vues supprimées et clés étrangères suspendues pendant l'opération (les `ALTER ... ADD COLUMN` déjà appliqués sont ignorés) ;
3. si une migration a tourné, `schema.sql` est rejoué pour recréer les vues ;
4. la configuration utilisateur est recopiée dans `score_config` / `modes_config`.

Les vues sont recréées à chaque démarrage : modifier une vue ne demande pas de migration, modifier une table oui.

## Où sont les données personnelles

Uniquement dans `db/dynastasie.db`, `data/`, `config/user.toml` et `secrets.env`, tous ignorés par git et exclus de l'image Docker.
