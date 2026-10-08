from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "db" / "dynastasie.db"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def _run_migrations(conn: sqlite3.Connection) -> None:
    for col, coltype in [
        ("hrv", "REAL"),
        ("rhr", "REAL"),
        ("sleep_min", "REAL"),
        ("steps", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE vigueur_entries ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("ALTER TABLE npt_notes ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
    except sqlite3.OperationalError:
        pass
    # score_semaine sémantique changée : 0-100 (100=parfait), + hrv_delta_s1
    try:
        conn.execute("ALTER TABLE semaines_audit ADD COLUMN hrv_delta_s1 REAL")
    except sqlite3.OperationalError:
        pass
    # Renommage friction_score -> score_semaine (aligné avec v_score_semaine)
    try:
        conn.execute("ALTER TABLE semaines_audit RENAME COLUMN friction_score TO score_semaine")
    except sqlite3.OperationalError:
        pass
    # objectifs : priorite (ancienne DB utilisait niveau_energie_requis)
    try:
        conn.execute("ALTER TABLE objectifs ADD COLUMN priorite INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    # Workout tracking — nouvelles colonnes
    for stmt in [
        "ALTER TABLE exercise_library ADD COLUMN load_formula TEXT NOT NULL DEFAULT 'weight'",
        "ALTER TABLE workout_sessions ADD COLUMN bodyweight_kg REAL",
        "ALTER TABLE workout_sessions ADD COLUMN session_volume_kg REAL",
        "ALTER TABLE workout_session_sets ADD COLUMN completed INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE workout_session_sets ADD COLUMN load_kg REAL",
        "ALTER TABLE workout_template_exercises ADD COLUMN emom_interval_sec INTEGER",
        "ALTER TABLE workout_session_exercises ADD COLUMN emom_interval_sec INTEGER",
        "ALTER TABLE workout_sessions ADD COLUMN intervals_activity_id TEXT",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_intervals "
            "ON workout_sessions(intervals_activity_id)"
        )
    except sqlite3.OperationalError:
        pass
    # positions_investissement — suivi des frais annuels (TER)
    try:
        conn.execute("ALTER TABLE positions_investissement ADD COLUMN frais_pct REAL")
    except sqlite3.OperationalError:
        pass
    # focus_sessions — flag pilier(s) contribué(s) par la session (CSV)
    try:
        conn.execute("ALTER TABLE focus_sessions ADD COLUMN piliers TEXT")
    except sqlite3.OperationalError:
        pass
    # Audit Hebdo v2 (2026-08-31, cf. .github/PLAN_AUDIT_HEBDO_V2.md §3/§8.1)
    for col, coltype in [
        ("forge_jours_engagement_mois", "INTEGER"),
        ("jours_engagement_semaine", "INTEGER DEFAULT 0"),
        ("forge_drill_engagement", "TEXT"),
        ("forge_hardskills_sujet", "TEXT"),
        ("forge_pro_champ_1", "TEXT"),
        ("forge_pro_champ_2", "TEXT"),
        ("forge_pro_champ_3", "TEXT"),
        ("forge_pro_blocage", "TEXT"),
        ("forge_pro_dependance_tiers", "INTEGER"),
        ("logos_avancement_uvs", "TEXT"),
        ("logos_projet_tx", "TEXT"),
        ("logos_article_analyse", "TEXT"),
        ("alignement_prerequis", "TEXT"),
        ("alignement_stage", "TEXT"),
        ("alignement_friction_semaine", "TEXT"),
        ("plan_drill_engagement", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE audit_narrative ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass
    for col in ("focus_engagement_min", "focus_projets_fond_min"):
        try:
            conn.execute(f"ALTER TABLE semaines_audit ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass
    # Audit Annuel — Clarté & Alignement Personnel (Deci & Ryan / ACT), 5 modules
    for col, coltype in [
        ("m1_note_recuperation", "INTEGER"),
        ("m1_note_signaux", "INTEGER"),
        ("m1_note_soupapes", "INTEGER"),
        ("m1_note_respiration", "INTEGER"),
        ("m1_cout_allostasie", "TEXT"),
        ("m1_sources_ressourcement", "TEXT"),
        ("m2_note_flow", "INTEGER"),
        ("m2_note_fierte", "INTEGER"),
        ("m2_note_effort", "INTEGER"),
        ("m2_note_priorites", "INTEGER"),
        ("m2_flow_moment1", "TEXT"),
        ("m2_flow_moment2", "TEXT"),
        ("m2_friction_tache1", "TEXT"),
        ("m2_friction_tache2", "TEXT"),
        ("m3_note_securite", "INTEGER"),
        ("m3_note_limites", "INTEGER"),
        ("m3_note_etancheite", "INTEGER"),
        ("m3_note_mutualite", "INTEGER"),
        ("m3_oui_complaisance1", "TEXT"),
        ("m3_oui_complaisance2", "TEXT"),
        ("m3_arbitrage_nourrir", "TEXT"),
        ("m3_arbitrage_reguler", "TEXT"),
        ("m4_note_locus", "INTEGER"),
        ("m4_note_autocompassion", "INTEGER"),
        ("m4_note_courage", "INTEGER"),
        ("m4_note_plasticite", "INTEGER"),
        ("m4_fait_brut", "TEXT"),
        ("m4_interpretation_initiale", "TEXT"),
        ("m4_variable_controle", "TEXT"),
        ("m4_regle_systemique", "TEXT"),
        ("m5_autonomie_objectif", "TEXT"),
        ("m5_autonomie_indicateur", "TEXT"),
        ("m5_maitrise_objectif", "TEXT"),
        ("m5_maitrise_indicateur", "TEXT"),
        ("m5_contribution_objectif", "TEXT"),
        ("m5_contribution_indicateur", "TEXT"),
        ("m5_habitude_declencheur", "TEXT"),
        ("m5_habitude_comportement", "TEXT"),
        ("m5_distraction_declencheur", "TEXT"),
        ("m5_distraction_comportement", "TEXT"),
        ("m5_regulation_declencheur", "TEXT"),
        ("m5_regulation_comportement", "TEXT"),
        ("objectif_m1", "INTEGER"),
        ("objectif_m2", "INTEGER"),
        ("objectif_m3", "INTEGER"),
        ("objectif_m4", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE audit_annuel ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass
    # Force-recreation of views that use CREATE VIEW IF NOT EXISTS in schema.sql
    # (DROP ensures schema changes are picked up on existing DBs)
    conn.executescript("""
        DROP VIEW IF EXISTS v_progression_quotidienne;
        CREATE VIEW v_progression_quotidienne AS
        WITH screen_day AS (
            SELECT
                substr(session_start, 1, 10)        AS date,
                SUM(duration_seconds) / 60.0        AS screen_min
            FROM screen_sessions
            WHERE package IN (SELECT package FROM apps_distrayantes)
            GROUP BY substr(session_start, 1, 10)
        ),
        foc AS (
            SELECT date_session AS d, SUM(duree_min) AS focus_min
            FROM focus_sessions
            GROUP BY date_session
        ),
        foc_strat AS (
            SELECT date_session AS d, SUM(duree_min) AS focus_strat_min
            FROM focus_sessions
            WHERE piliers LIKE '%FORGE_ENGAGEMENT%'
               OR piliers LIKE '%FORGE_HARDSKILLS%'
               OR piliers LIKE '%FORGE_PRO%'
               OR piliers LIKE '%LOGOS%'
            GROUP BY date_session
        ),
        scores AS (
            SELECT
                hl.date_log,
                hl.semaine_id,
                sa2.mode_actif                AS mode_actif,
                ve.sleep_min,
                ve.moving_time_min,
                ve.steps,
                COALESCE(f.focus_min,        0)  AS focus_min,
                COALESCE(fs.focus_strat_min, 0)  AS focus_strat_min,
                COALESCE(sd.screen_min,      0)  AS screen_min,
                CASE
                    WHEN COALESCE(ve.moving_time_min, 0) >= 60 THEN 1
                    WHEN EXISTS(SELECT 1 FROM plan_entrainement pe
                                WHERE pe.date_jour = hl.date_log AND pe.is_repos = 1) THEN 1
                    ELSE 0
                END AS ok_sport,
                CASE WHEN COALESCE(ve.sleep_min, 0) >= 450  THEN 1 ELSE 0 END AS ok_sommeil,
                CASE WHEN COALESCE(ve.steps,     0) >= 10000 THEN 1 ELSE 0 END AS ok_pas,
                CASE
                    WHEN sa2.mode_actif = 'Entreprise' THEN CASE WHEN COALESCE(f.focus_min, 0) >= 150 THEN 1 ELSE 0 END
                    WHEN sa2.mode_actif = 'ecole'        THEN CASE WHEN COALESCE(f.focus_min, 0) >= 240 THEN 1 ELSE 0 END
                    ELSE                                     CASE WHEN COALESCE(f.focus_min, 0) >= 90  THEN 1 ELSE 0 END
                END AS ok_focus,
                CASE WHEN COALESCE(fs.focus_strat_min, 0) >= 30 THEN 1 ELSE 0 END AS ok_focus_strat,
                CASE
                    WHEN COALESCE(sd.screen_min, 0) < 30 THEN 1
                    WHEN sd_prev.screen_min IS NOT NULL
                     AND COALESCE(sd.screen_min, 0) < sd_prev.screen_min THEN 1
                    ELSE 0
                END AS ok_ecran
            FROM habitude_logs hl
            LEFT JOIN semaines_audit  sa2     ON sa2.id        = hl.semaine_id
            LEFT JOIN vigueur_entries ve      ON ve.date_entry = hl.date_log
            LEFT JOIN foc f                   ON f.d           = hl.date_log
            LEFT JOIN foc_strat fs            ON fs.d          = hl.date_log
            LEFT JOIN screen_day sd           ON sd.date       = hl.date_log
            LEFT JOIN screen_day sd_prev      ON sd_prev.date  = date(hl.date_log, '-7 days')
        )
        SELECT
            date_log,
            semaine_id,
            mode_actif,
            sleep_min,
            moving_time_min,
            steps,
            focus_min,
            focus_strat_min,
            screen_min,
            ok_sport,
            ok_sommeil,
            ok_pas,
            ok_focus,
            ok_focus_strat,
            ok_ecran,
            (ok_sport + ok_sommeil + ok_pas + ok_focus + ok_focus_strat + ok_ecran)          AS score_6,
            ROUND(100.0 * (ok_sport + ok_sommeil + ok_pas + ok_focus + ok_focus_strat + ok_ecran) / 6.0, 1) AS pct,
            CASE
                WHEN (ok_sport + ok_sommeil + ok_pas + ok_focus + ok_focus_strat + ok_ecran) = 6  THEN 'S'
                WHEN (ok_sport + ok_sommeil + ok_pas + ok_focus + ok_focus_strat + ok_ecran) >= 5 THEN 'A'
                WHEN (ok_sport + ok_sommeil + ok_pas + ok_focus + ok_focus_strat + ok_ecran) >= 4 THEN 'B'
                WHEN (ok_sport + ok_sommeil + ok_pas + ok_focus + ok_focus_strat + ok_ecran) >= 3 THEN 'C'
                ELSE 'D'
            END AS rank
        FROM scores;
    """)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS npt_personnes (
            id          INTEGER PRIMARY KEY,
            prenom      TEXT    NOT NULL,
            nom         TEXT    NOT NULL DEFAULT '',
            liens       TEXT    NOT NULL DEFAULT '',
            etat        TEXT    NOT NULL DEFAULT 'En vie et proche'
                                CHECK (etat IN ('En vie et proche', 'En vie et distant', 'Mort')),
            proximite   INTEGER,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS npt_notes (
            id          INTEGER PRIMARY KEY,
            personne_id INTEGER NOT NULL REFERENCES npt_personnes(id) ON DELETE CASCADE,
            date_note   TEXT,
            contenu     TEXT    NOT NULL,
            source      TEXT    NOT NULL DEFAULT 'manual'
                                CHECK (source IN ('manual')),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        -- Migration : ajoute source si la table existait déjà sans cette colonne
        CREATE INDEX IF NOT EXISTS idx_npt_notes_personne ON npt_notes(personne_id, date_note DESC);
        CREATE TABLE IF NOT EXISTS audit_trimestriel (
            id                  INTEGER PRIMARY KEY,
            saison              TEXT    NOT NULL
                                 CHECK (saison IN ('Hiver','Printemps','Été','Automne')),
            annee               INTEGER NOT NULL,
            p1_accomplissements TEXT,
            p1_burnout          TEXT,
            p1_energie          TEXT,
            p2_direction        TEXT,
            p2_piliers          TEXT,
            p2_intentions       TEXT,
            p3_concretisation   TEXT,
            p3_frictions        TEXT,
            p3_echelle          TEXT,
            p4_solutions        TEXT,
            p4_non_negotiable   TEXT,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(saison, annee)
        );
        CREATE TABLE IF NOT EXISTS audit_annuel (
            id          INTEGER PRIMARY KEY,
            annee       INTEGER NOT NULL UNIQUE,
            date_audit  TEXT,
            theme1      TEXT,
            theme2      TEXT,
            theme3      TEXT,
            theme4      TEXT,
            conclusion  TEXT,
            m1_note_recuperation       INTEGER,
            m1_note_signaux            INTEGER,
            m1_note_soupapes           INTEGER,
            m1_note_respiration        INTEGER,
            m1_cout_allostasie         TEXT,
            m1_sources_ressourcement   TEXT,
            m2_note_flow               INTEGER,
            m2_note_fierte             INTEGER,
            m2_note_effort             INTEGER,
            m2_note_priorites          INTEGER,
            m2_flow_moment1            TEXT,
            m2_flow_moment2            TEXT,
            m2_friction_tache1         TEXT,
            m2_friction_tache2         TEXT,
            m3_note_securite           INTEGER,
            m3_note_limites            INTEGER,
            m3_note_etancheite         INTEGER,
            m3_note_mutualite          INTEGER,
            m3_oui_complaisance1       TEXT,
            m3_oui_complaisance2       TEXT,
            m3_arbitrage_nourrir       TEXT,
            m3_arbitrage_reguler       TEXT,
            m4_note_locus              INTEGER,
            m4_note_autocompassion     INTEGER,
            m4_note_courage            INTEGER,
            m4_note_plasticite         INTEGER,
            m4_fait_brut               TEXT,
            m4_interpretation_initiale TEXT,
            m4_variable_controle       TEXT,
            m4_regle_systemique        TEXT,
            m5_autonomie_objectif      TEXT,
            m5_autonomie_indicateur    TEXT,
            m5_maitrise_objectif       TEXT,
            m5_maitrise_indicateur     TEXT,
            m5_contribution_objectif   TEXT,
            m5_contribution_indicateur TEXT,
            m5_habitude_declencheur    TEXT,
            m5_habitude_comportement   TEXT,
            m5_distraction_declencheur TEXT,
            m5_distraction_comportement TEXT,
            m5_regulation_declencheur  TEXT,
            m5_regulation_comportement TEXT,
            objectif_m1 INTEGER,
            objectif_m2 INTEGER,
            objectif_m3 INTEGER,
            objectif_m4 INTEGER,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS vigueur_personal_records (
            distance_m       REAL    NOT NULL,
            duree_sec        INTEGER NOT NULL,
            date_realisation TEXT    NOT NULL,
            source           TEXT    DEFAULT 'intervals',
            PRIMARY KEY (distance_m, date_realisation)
        );
        CREATE TABLE IF NOT EXISTS vigueur_predictions_logs (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp          TEXT    DEFAULT CURRENT_TIMESTAMP,
            distance_cible_m   REAL    NOT NULL,
            temps_predit_sec   INTEGER NOT NULL,
            allure_predite_str TEXT    NOT NULL,
            facteur_b_utilise  REAL    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS strava_oauth_tokens (
            id               INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            access_token     TEXT    NOT NULL,
            refresh_token    TEXT    NOT NULL,
            expires_at       INTEGER NOT NULL,
            last_pr_sync_epoch INTEGER
        );
        CREATE TABLE IF NOT EXISTS sync_checkpoints (
            source      TEXT PRIMARY KEY,
            last_date   TEXT,
            updated_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS system_freezes (
            id          INTEGER PRIMARY KEY,
            date_debut  TEXT NOT NULL,
            date_fin    TEXT NOT NULL,
            raison      TEXT NOT NULL,
            piliers     TEXT,
            contexte    TEXT,
            statut      TEXT NOT NULL DEFAULT 'actif'
                        CHECK (statut IN ('actif','termine')),
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
    """)
    try:
        conn.execute("ALTER TABLE semaines_audit ADD COLUMN is_frozen INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _drop_legacy_notion(conn: sqlite3.Connection) -> None:
    """Nettoie les restes de l'ancienne synchronisation Notion (idempotent)."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(semaines_audit)")]
    if "notion_page_id" in cols:
        try:
            conn.execute("ALTER TABLE semaines_audit DROP COLUMN notion_page_id")
        except sqlite3.OperationalError:
            pass
    conn.execute("UPDATE npt_notes SET source = 'manual' WHERE source = 'notion'")
    conn.execute("UPDATE logs_systeme SET type_sync = 'mode' WHERE type_sync = 'notion'")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        _run_migrations(conn)
        _drop_legacy_notion(conn)
    print(f"[DB] Initialisé : {DB_PATH}")


@contextmanager
def db_session():
    """Context manager transactionnel. Commite on exit, rollback on exception."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
