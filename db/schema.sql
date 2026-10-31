-- DynaStasie — SQLite Schema v1
-- Schéma SQLite local-first — hub hebdomadaire semaines_audit
-- Grain central : semaine ISO (lundi)
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ─────────────────────────────────────────────────────────────────
-- HUB CENTRAL
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS semaines_audit (
    id                      INTEGER PRIMARY KEY,
    week_start              TEXT    NOT NULL UNIQUE, -- ISO "2026-05-18"
    week_label              TEXT    NOT NULL,        -- "Audit S21 – 18/05/2026"

    -- VIGUEUR / Intervals.icu
    ctl                     REAL,
    atl                     REAL,
    tsb                     REAL,
    tss                     REAL,
    ctl_delta               REAL,
    vo2max                  REAL,
    distance_km             REAL,
    temps_sport_min         REAL,

    -- TEMPS ÉCRAN / Samsung ADB
    screen_time_min         REAL,
    top_apps_text           TEXT,

    -- FINANCE
    capital_eur             REAL,
    investissement_pea      INTEGER DEFAULT 0,
    av_fonds_euros          INTEGER DEFAULT 0,
    av_uc_diversifies       INTEGER DEFAULT 0,

    -- RÉSONNANCE
    social                  TEXT CHECK (social IN ('Connecté/Ressourcé','Isolé',NULL)),
    pivot                   TEXT,

    -- ROLLUPS calculés (cascade depuis focus_sessions + habitude_logs)
    deep_focus_min          REAL,
    nuits_bonne_recup       INTEGER,
    sessions_lecture        INTEGER,
    sessions_sport          INTEGER,
    sessions_jeune          INTEGER,
    score_semaine           REAL,   -- score semaine 0-100 (100=parfait)
    hrv_delta_s1            REAL,   -- delta HRV médiane vs semaine précédente
    focus_engagement_min     REAL,   -- minutes focus taguées FORGE_ENGAGEMENT (rollup cascade)
    focus_projets_fond_min  REAL,   -- minutes focus FORGE_HARDSKILLS+FORGE_PRO+LOGOS (rollup cascade)
    alertes_json            TEXT,

    -- META
    mode_actif              TEXT CHECK (mode_actif IN ('ecole','entreprise')),
    created_at              TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS logs_systeme (
    id            INTEGER PRIMARY KEY,
    timestamp     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    type_sync     TEXT    NOT NULL
                   CHECK (type_sync IN ('vigueur','screen_time','finance','focus','habits','mode')),
    source        TEXT,
    semaine_id    INTEGER REFERENCES semaines_audit(id),
    statut        TEXT    NOT NULL CHECK (statut IN ('ok','erreur','partiel')),
    message       TEXT,
    payload_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_ts   ON logs_systeme(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_type ON logs_systeme(type_sync);

-- ─────────────────────────────────────────────────────────────────
-- FOCUS — Productivité WRK v.2 (remplace bot Discord Prométhée)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS focus_sessions (
    id                  INTEGER PRIMARY KEY,
    numero_session      INTEGER UNIQUE,
    date_session        TEXT    NOT NULL,
    heure_debut         TEXT    NOT NULL,
    heure_fin           TEXT,
    duree_min           REAL,
    heures_manuelles    REAL,
    channel             TEXT    DEFAULT 'local',
    piliers             TEXT,   -- pilier(s) taggés, CSV parmi FORGE/LOGOS/VIGUEUR/RESONNANCE/SYSTEME
    source              TEXT    NOT NULL DEFAULT 'local'
                         CHECK (source IN ('discord_wrk','local_cli','manual')),
    semaine_id          INTEGER REFERENCES semaines_audit(id),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (date_session, heure_debut, source)
);
CREATE INDEX IF NOT EXISTS idx_focus_date ON focus_sessions(date_session DESC);

CREATE VIEW IF NOT EXISTS v_deep_focus_hebdo AS
SELECT
    semaine_id,
    COUNT(*)                                                           AS nb_sessions,
    ROUND(SUM(COALESCE(heures_manuelles * 60, duree_min)), 1)         AS minutes_totales,
    ROUND(SUM(COALESCE(heures_manuelles * 60, duree_min)) / 60.0, 2) AS heures_decimales
FROM focus_sessions
GROUP BY semaine_id;

-- ─────────────────────────────────────────────────────────────────
-- HABITUDES — Tracker quotidien (grain : jour)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS habitude_logs (
    id                  INTEGER PRIMARY KEY,
    date_log            TEXT    NOT NULL UNIQUE,
    jour_label          TEXT,
    semaine_id          INTEGER REFERENCES semaines_audit(id),

    bonne_recup_8h9h    INTEGER NOT NULL DEFAULT 0,
    deep_focus_90min    INTEGER NOT NULL DEFAULT 0,
    lecture_10min       INTEGER NOT NULL DEFAULT 0,
    sport_marche_45min  INTEGER NOT NULL DEFAULT 0,
    jeune_intermittent  INTEGER NOT NULL DEFAULT 0,

    status              TEXT,
    note_libre          TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_hablog_semaine ON habitude_logs(semaine_id);

DROP VIEW IF EXISTS v_progression_quotidienne;
CREATE VIEW v_progression_quotidienne AS
-- Journée parfaite (6 critères) : sport (ou repos planifié) · sommeil · pas · focus deep-work
-- selon le mode · focus stratégique (Forge/Logos) · écran distraction sous le seuil OU en baisse
-- vs même jour S-7. Seuils : v_score_params (config/user.toml) ; seuils de focus : modes_config.
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
            WHEN COALESCE(ve.moving_time_min, 0) >= p.jour_sport_min THEN 1
            WHEN EXISTS(SELECT 1 FROM plan_entrainement pe
                        WHERE pe.date_jour = hl.date_log AND pe.is_repos = 1) THEN 1
            ELSE 0
        END AS ok_sport,
        CASE WHEN COALESCE(ve.sleep_min, 0) >= p.jour_sommeil_min THEN 1 ELSE 0 END AS ok_sommeil,
        CASE WHEN COALESCE(ve.steps,     0) >= p.jour_pas          THEN 1 ELSE 0 END AS ok_pas,
        CASE
            WHEN mc.code IS NOT NULL THEN CASE WHEN COALESCE(f.focus_min, 0) >= mc.focus_jour_min THEN 1 ELSE 0 END
            ELSE                          CASE WHEN COALESCE(f.focus_min, 0) >= p.jour_focus_defaut_min THEN 1 ELSE 0 END
        END AS ok_focus,
        CASE WHEN COALESCE(fs.focus_strat_min, 0) >= p.jour_focus_strat_min THEN 1 ELSE 0 END AS ok_focus_strat,
        CASE
            WHEN COALESCE(sd.screen_min, 0) < p.jour_ecran_max_min THEN 1
            WHEN sd_prev.screen_min IS NOT NULL
             AND COALESCE(sd.screen_min, 0) < sd_prev.screen_min THEN 1
            ELSE 0
        END AS ok_ecran
    FROM habitude_logs hl
    CROSS JOIN v_score_params p
    LEFT JOIN semaines_audit  sa2     ON sa2.id        = hl.semaine_id
    LEFT JOIN modes_config    mc      ON mc.code       = sa2.mode_actif
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

-- ─────────────────────────────────────────────────────────────────
-- VIGUEUR — Intervals.icu
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vigueur_entries (
    id              INTEGER PRIMARY KEY,
    date_entry      TEXT    NOT NULL UNIQUE,
    ctl             REAL,
    atl             REAL,
    tsb             REAL,
    tss             REAL,
    vo2max          REAL,
    distance_km     REAL,
    moving_time_min REAL,
    hrv             REAL,
    rhr             REAL,
    sleep_min       REAL,
    steps           INTEGER,
    source          TEXT    NOT NULL DEFAULT 'intervals.icu',
    fetched_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_vigueur_date ON vigueur_entries(date_entry DESC);

-- ─────────────────────────────────────────────────────────────────
-- TEMPS ÉCRAN — Samsung ADB
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS screen_sessions (
    id               INTEGER PRIMARY KEY,
    package          TEXT    NOT NULL,
    app_name         TEXT    NOT NULL,
    session_start    TEXT    NOT NULL,
    session_end      TEXT    NOT NULL,
    duration_seconds REAL    NOT NULL,
    semaine_id       INTEGER REFERENCES semaines_audit(id),
    UNIQUE (package, session_start)
);
CREATE INDEX IF NOT EXISTS idx_screen_start ON screen_sessions(session_start DESC);

-- ─────────────────────────────────────────────────────────────────
-- FINANCE
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS comptes (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    type_compte  TEXT NOT NULL,
    libelle      TEXT NOT NULL,
    classe_actif TEXT NOT NULL
                  CHECK (classe_actif IN ('liquidites','livrets','actions','fonds_euros','immobilier')),
    actif        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS soldes_comptes (
    id            INTEGER PRIMARY KEY,
    compte_id     INTEGER NOT NULL REFERENCES comptes(id),
    date_snapshot TEXT    NOT NULL,
    solde         REAL    NOT NULL,
    semaine_id    INTEGER REFERENCES semaines_audit(id),
    UNIQUE (compte_id, date_snapshot)
);

CREATE TABLE IF NOT EXISTS transactions (
    id         INTEGER PRIMARY KEY,
    date_op    TEXT    NOT NULL,
    libelle    TEXT    NOT NULL,
    montant    REAL    NOT NULL,
    source     TEXT    NOT NULL,
    compte_id  INTEGER REFERENCES comptes(id),
    categorie  TEXT    NOT NULL DEFAULT 'non_categorise'
                CHECK (categorie IN ('revenus','fixes','variables',
                       'epargne_investissement','virements_internes',
                       'virements_internes_revolut','non_categorise')),
    UNIQUE (date_op, libelle, montant, source)
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date_op DESC);
CREATE INDEX IF NOT EXISTS idx_tx_cat  ON transactions(categorie);

CREATE TABLE IF NOT EXISTS positions_investissement (
    id             INTEGER PRIMARY KEY,
    date_snapshot  TEXT    NOT NULL,
    compte_id      INTEGER NOT NULL REFERENCES comptes(id),
    categorie      TEXT,
    support        TEXT    NOT NULL,
    nb_parts       REAL,
    cotation       REAL,
    valeur         REAL    NOT NULL,
    plus_value     REAL,
    perf_ytd       TEXT,
    frais_pct      REAL,
    UNIQUE (date_snapshot, compte_id, support)
);

CREATE TABLE IF NOT EXISTS budgets_mensuels (
    id             INTEGER PRIMARY KEY,
    mois_reference TEXT    NOT NULL UNIQUE,
    total_revenus  REAL    NOT NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS revenus_budget (
    id        INTEGER PRIMARY KEY,
    budget_id INTEGER NOT NULL REFERENCES budgets_mensuels(id),
    nom       TEXT    NOT NULL,
    montant   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS depenses_budget (
    id            INTEGER PRIMARY KEY,
    budget_id     INTEGER NOT NULL REFERENCES budgets_mensuels(id),
    categorie     TEXT    NOT NULL,
    nom           TEXT    NOT NULL,
    montant       REAL    NOT NULL,
    suivi_mensuel INTEGER NOT NULL DEFAULT 0,
    detail        TEXT
);

-- ─────────────────────────────────────────────────────────────────
-- FORGE & LOGOS
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sequences_mode (
    id          INTEGER PRIMARY KEY,
    numero      INTEGER NOT NULL,
    lieu        TEXT    NOT NULL CHECK (lieu IN ('ecole','entreprise')),
    date_debut  TEXT    NOT NULL,
    date_fin    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS objectifs (
    id                     INTEGER PRIMARY KEY,
    titre                  TEXT    NOT NULL,
    pilier                 TEXT    NOT NULL
                            CHECK (pilier IN ('FORGE','LOGOS','VIGUEUR','RESONNANCE','SYSTEME')),
    statut                 TEXT    NOT NULL DEFAULT 'actif'
                            CHECK (statut IN ('actif','en_pause','termine','abandonne')),
    date_cible             TEXT,
    description            TEXT,
    priorite  INTEGER DEFAULT 1 CHECK (priorite BETWEEN 1 AND 3),
    created_at             TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at             TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Calendrier d'entraînement importé (CSV Google Calendar) — sert de source pour
-- is_deload_week et "jour de repos planifié" dans le scoring hebdo/quotidien (cf.
-- .github/PLAN_AUDIT_HEBDO_V2.md §8.1/§9.2). Une ligne = un événement calendrier,
-- plusieurs lignes possibles pour une même date_jour (ex: bascule de saison).
CREATE TABLE IF NOT EXISTS plan_entrainement (
    id            INTEGER PRIMARY KEY,
    date_jour     TEXT    NOT NULL,           -- ISO "2026-09-23"
    titre         TEXT    NOT NULL,
    description   TEXT,
    mesocycle     TEXT,                       -- "M1-S1", "M1-S4", "S2-Été", "Kickoff Automne"... NULL si hors cycle régulier
    type_semaine  TEXT    NOT NULL DEFAULT 'hors_cycle'
                   CHECK (type_semaine IN ('charge','hardcore','decharge','kickoff','hors_cycle')),
    is_repos      INTEGER NOT NULL DEFAULT 0, -- dérivé du titre ("Repos" présent) à l'import
    saison        TEXT CHECK (saison IN ('Hiver','Printemps','Ete','Automne')),
    source_csv    TEXT,                       -- fichier CSV d'origine, traçabilité
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(date_jour, titre)
);
CREATE INDEX IF NOT EXISTS idx_plan_entrainement_date ON plan_entrainement(date_jour);

CREATE TABLE IF NOT EXISTS taches (
    id            INTEGER PRIMARY KEY,
    titre         TEXT    NOT NULL,
    description   TEXT,
    objectif_id   INTEGER REFERENCES objectifs(id),
    priorite      INTEGER NOT NULL DEFAULT 3 CHECK (priorite BETWEEN 1 AND 3),
    statut        TEXT    NOT NULL DEFAULT 'todo'
                   CHECK (statut IN ('todo','en_cours','fait','annule')),
    date_debut    TEXT,              -- début de la période (ISO date ou datetime)
    date_echeance TEXT,              -- fin / deadline
    heure_debut   TEXT,              -- "HH:MM"
    heure_fin     TEXT,              -- "HH:MM"
    completed_at  TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_taches_priorite ON taches(priorite, statut);

CREATE TABLE IF NOT EXISTS cours_ecole (
    id            INTEGER PRIMARY KEY,
    semestre      TEXT,              -- NULL = ligne de référentiel (catalogue) ; sinon "A23 (TC01)"
    code          TEXT    NOT NULL,
    intitule      TEXT    NOT NULL,
    type_uv       TEXT,
    credits       INTEGER,
    note          TEXT,              -- note obtenue pour une ligne d'historique
    description   TEXT,
    disponibilite TEXT,              -- "Automne" | "Printemps" | "Automne, Printemps"
    competences   TEXT,              -- codes référentiel C1-1, C5-2, ... séparés par virgule
    en_cours      INTEGER NOT NULL DEFAULT 0,
    valide        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (semestre, code)
);

-- GPA officiels (relevé manuel, saisi/édité depuis la page LOGOS) — ligne unique id=1
CREATE TABLE IF NOT EXISTS logos_gpa (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    tc_gpa            REAL,
    tc_uvs            INTEGER,
    branche_gpa       REAL,
    branche_uvs       INTEGER,
    global_gpa        REAL,
    global_uvs        INTEGER,
    cible_gpa         REAL,
    cible_uvs         INTEGER,
    cs_gpa            REAL,
    cs_uvs            INTEGER,
    tm_gpa            REAL,
    tm_uvs            INTEGER,
    tsh_gpa           REAL,
    tsh_uvs           INTEGER,
    semestres_passes  INTEGER,
    updated_at        TEXT
);

-- ─────────────────────────────────────────────────────────────────
-- AUDIT NARRATIF — Template hebdo Sections II–VI
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_narrative (
    id                   INTEGER PRIMARY KEY,
    semaine_id           INTEGER NOT NULL UNIQUE REFERENCES semaines_audit(id),
    -- II — ÉTAT DU SYSTÈME (STASIE)
    jauge_energie        INTEGER CHECK (jauge_energie BETWEEN 1 AND 10),
    alerte_rouge         INTEGER NOT NULL DEFAULT 0,  -- 0=NON, 1=OUI
    correction_immediate TEXT,
    -- III — PENTAGONE (réflexions par pilier) — legacy narratif, plus alimenté par le form v2
    pentagone_vigueur    TEXT,   -- Force / Endurance / Santé
    pentagone_logos      TEXT,   -- GPA / Veille / Huberman
    pentagone_forge      TEXT,   -- Orchestration / projets / entreprise
    pentagone_resonance  TEXT,   -- Service invisible / Relations / Mémoire
    pentagone_systeme    TEXT,   -- Capture & Planification / Audit habits
    -- IV — L'OMBRE (Anti-Soi)
    ombre_mediocrite     TEXT,   -- Tâche critique reportée ?
    ombre_consommateur   TEXT,   -- Écran créatif ou passif ?
    ombre_menteur        TEXT,   -- Intégrité du journal ?
    -- V — ALIGNEMENT — legacy, remplacé par alignement_prerequis/alignement_stage
    alignement_fmir      TEXT,   -- legacy
    -- VI — PLAN DE BATAILLE
    plan_priorite_unique TEXT,   -- The One Thing
    plan_ajustement_algo TEXT,   -- legacy, remplacé par plan_drill_engagement

    -- FORGE — Engagement (critère configurable ; noms renommés par la migration 004)
    forge_jours_engagement_mois   INTEGER,  -- jours d'engagement ce mois-ci
    jours_engagement_semaine          INTEGER DEFAULT 0,  -- jours d'engagement cette semaine (critère du score)
    forge_drill_engagement      TEXT,     -- pratique de la semaine — faite ou non

    -- FORGE — Hard Skills & Problématiques Critiques (toujours affiché)
    forge_hardskills_sujet     TEXT,     -- Sujet technique traité cette semaine

    -- FORGE — Entreprise (affiché uniquement si mode_actif == 'Entreprise')
    forge_pro_champ_1      TEXT,
    forge_pro_champ_2     TEXT,
    forge_pro_champ_3      TEXT,
    forge_pro_blocage          TEXT,
    forge_pro_dependance_tiers INTEGER,  -- 0/1

    -- LOGOS — Académique & Recherche
    logos_avancement_uvs   TEXT,
    logos_projet_tx        TEXT,
    logos_article_analyse  TEXT,

    -- V. ALIGNEMENT OPÉRATIONNEL — nouveaux champs (remplacent alignement_fmir, legacy)
    alignement_prerequis TEXT,
    alignement_stage            TEXT,
    alignement_friction_semaine     TEXT,

    -- VI. PLAN DE BATAILLE — nouveau champ (remplace plan_ajustement_algo)
    plan_drill_engagement   TEXT,

    created_at           TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ─────────────────────────────────────────────────────────────────
-- VUES SQL — Query Layer
-- ─────────────────────────────────────────────────────────────────
-- Score semaine 0-100 (100 = semaine parfaite, 10 critères équipondérés)
-- Modèle v2 (2026-08-31, cf. .github/PLAN_AUDIT_HEBDO_V2.md §8) — remplace
-- v_friction_hebdo (ancienne échelle 0-8 pénalités) et le modèle v1 (lecture/CTLΔ/HRVΔ).
-- ⚠️ Vue recalculée à la volée : rétroactif sur tout l'historique (option A du §8.0,
-- assumée explicitement — les scores S1-S35 baissent mécaniquement, cf. §8.0).
DROP VIEW IF EXISTS v_friction_hebdo;
DROP VIEW IF EXISTS v_score_semaine;
CREATE VIEW v_score_semaine AS
WITH
week_habits AS (
    SELECT
        semaine_id,
        COALESCE(SUM(lecture_10min), 0) AS lectures
    FROM habitude_logs
    GROUP BY semaine_id
),
week_vigueur AS (
    SELECT
        sa.id                                                                    AS semaine_id,
        COALESCE(SUM(ve.moving_time_min), 0)                                    AS entrainement_min,
        COALESCE(SUM(ve.steps),           0)                                    AS pas_total,
        AVG(ve.sleep_min)                                                       AS sleep_moy,
        COALESCE(SUM(CASE WHEN ve.moving_time_min >= p.sem_seance_duree_min THEN 1 ELSE 0 END), 0) AS seances
    FROM semaines_audit sa
    CROSS JOIN v_score_params p
    LEFT JOIN vigueur_entries ve
        ON ve.date_entry >= sa.week_start
        AND ve.date_entry < date(sa.week_start, '+7 days')
    GROUP BY sa.id
),
-- Médiane HRV semaine courante (window function → select milieu trié)
week_hrv_ranked AS (
    SELECT
        sa.id                                                           AS semaine_id,
        ve.hrv,
        ROW_NUMBER() OVER (PARTITION BY sa.id ORDER BY ve.hrv)         AS rn,
        COUNT(ve.hrv)   OVER (PARTITION BY sa.id)                      AS cnt
    FROM semaines_audit sa
    LEFT JOIN vigueur_entries ve
        ON ve.date_entry >= sa.week_start
        AND ve.date_entry < date(sa.week_start, '+7 days')
        AND ve.hrv IS NOT NULL
),
week_hrv AS (
    SELECT semaine_id, ROUND(AVG(hrv), 1) AS hrv_moy
    FROM week_hrv_ranked
    WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
    GROUP BY semaine_id
),
-- Dernière semaine non gelée avant sa.week_start (ignore les semaines is_frozen)
prev_valid_week AS (
    SELECT
        sa.id AS semaine_id,
        (SELECT sa2.week_start FROM semaines_audit sa2
         WHERE sa2.week_start < sa.week_start AND sa2.is_frozen = 0
         ORDER BY sa2.week_start DESC LIMIT 1) AS prev_week_start
    FROM semaines_audit sa
),
-- Médiane HRV semaine précédente (non gelée)
prev_hrv_ranked AS (
    SELECT
        sa.id                                                           AS semaine_id,
        ve.hrv,
        ROW_NUMBER() OVER (PARTITION BY sa.id ORDER BY ve.hrv)         AS rn,
        COUNT(ve.hrv)   OVER (PARTITION BY sa.id)                      AS cnt
    FROM semaines_audit sa
    JOIN prev_valid_week pvw ON pvw.semaine_id = sa.id
    LEFT JOIN vigueur_entries ve
        ON pvw.prev_week_start IS NOT NULL
        AND ve.date_entry >= pvw.prev_week_start
        AND ve.date_entry <  date(pvw.prev_week_start, '+7 days')
        AND ve.hrv IS NOT NULL
),
prev_hrv AS (
    SELECT semaine_id, ROUND(AVG(hrv), 1) AS hrv_moy_prev
    FROM prev_hrv_ranked
    WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
    GROUP BY semaine_id
),
week_ecran AS (
    -- Apps listées dans apps_distrayantes uniquement, seuil 210 min/semaine
    SELECT
        sa.id AS semaine_id,
        ROUND(COALESCE(SUM(ss.duration_seconds), 0) / 60.0, 1) AS screen_distraction_min
    FROM semaines_audit sa
    LEFT JOIN screen_sessions ss
        ON substr(ss.session_start, 1, 10) >= sa.week_start
        AND substr(ss.session_start, 1, 10) < date(sa.week_start, '+7 days')
        AND ss.package IN (SELECT package FROM apps_distrayantes)
    GROUP BY sa.id
),
prev_ecran AS (
    -- screen time de la semaine précédente non gelée (même apps), pour fallback si > 210
    SELECT
        sa.id AS semaine_id,
        ROUND(COALESCE(SUM(ss.duration_seconds), 0) / 60.0, 1) AS screen_distraction_min_prev
    FROM semaines_audit sa
    JOIN prev_valid_week pvw ON pvw.semaine_id = sa.id
    LEFT JOIN screen_sessions ss
        ON pvw.prev_week_start IS NOT NULL
        AND substr(ss.session_start, 1, 10) >= pvw.prev_week_start
        AND substr(ss.session_start, 1, 10) < date(pvw.prev_week_start, '+7 days')
        AND ss.package IN (SELECT package FROM apps_distrayantes)
    GROUP BY sa.id
),
base AS (
    SELECT
        sa.id,
        sa.week_start,
        -- métriques brutes (utiles pour l'affichage)
        COALESCE(wv.seances,               0) AS seances,
        COALESCE(sa.deep_focus_min,        0) AS deep_focus_min,
        COALESCE(wv.entrainement_min,      0) AS entrainement_min,
        COALESCE(wv.pas_total,             0) AS pas_total,
        COALESCE(we.screen_distraction_min,0) AS screen_distraction_min,
        pe.screen_distraction_min_prev,
        sa.ctl_delta,
        sa.tsb,
        sa.mode_actif,
        sa.hrv_delta_s1,
        COALESCE(sa.focus_engagement_min,   0) AS focus_engagement_min,
        COALESCE(sa.focus_projets_fond_min, 0) AS focus_projets_fond_min,
        COALESCE(an.jours_engagement_semaine, 0) AS jours_engagement_semaine,
        wv.sleep_moy,
        whr.hrv_moy,
        phr.hrv_moy_prev,
        ROUND(whr.hrv_moy - phr.hrv_moy_prev, 1) AS hrv_delta,
        sa.social,
        EXISTS(SELECT 1 FROM plan_entrainement pe2
               WHERE pe2.date_jour >= sa.week_start
                 AND pe2.date_jour < date(sa.week_start, '+7 days')
                 AND pe2.type_semaine = 'decharge')            AS is_deload_week,
        EXISTS(SELECT 1 FROM audit_narrative WHERE semaine_id = sa.id) AS has_narrative
    FROM semaines_audit sa
    LEFT JOIN week_vigueur     wv  ON wv.semaine_id  = sa.id
    LEFT JOIN week_hrv         whr ON whr.semaine_id = sa.id
    LEFT JOIN prev_hrv         phr ON phr.semaine_id = sa.id
    LEFT JOIN week_ecran       we  ON we.semaine_id  = sa.id
    LEFT JOIN prev_ecran       pe  ON pe.semaine_id  = sa.id
    LEFT JOIN audit_narrative  an  ON an.semaine_id  = sa.id
),
-- seuils binaires (1 = critère validé) ; seuils : v_score_params, focus par mode : modes_config
crit AS (
    SELECT
        b.*,
        CASE WHEN b.entrainement_min >= p.sem_entrainement_min                  THEN 1 ELSE 0 END AS ok_entrainement,
        CASE WHEN b.seances          >= p.sem_seances                           THEN 1 ELSE 0 END AS ok_seances,
        CASE WHEN b.pas_total        >= p.sem_pas                               THEN 1 ELSE 0 END AS ok_pas,
        CASE WHEN COALESCE(b.sleep_moy, 0) >= p.sem_sommeil_min                 THEN 1 ELSE 0 END AS ok_sommeil,
        CASE WHEN b.is_deload_week
             THEN CASE WHEN COALESCE(b.tsb, -999) >= p.sem_tsb_decharge_min OR COALESCE(b.hrv_delta_s1, -999) >= 0 THEN 1 ELSE 0 END
             ELSE CASE WHEN COALESCE(b.tsb, -999) >= p.sem_tsb_min THEN 1 ELSE 0 END
        END                                                                                        AS ok_charge_fraicheur,
        CASE WHEN b.screen_distraction_min <= p.sem_ecran_max_min
                  OR b.screen_distraction_min < COALESCE(b.screen_distraction_min_prev, 0)
             THEN 1 ELSE 0 END                                                                     AS ok_ecran,
        CASE
            WHEN mc.code IS NOT NULL THEN CASE WHEN b.deep_focus_min >= mc.focus_semaine_min THEN 1 ELSE 0 END
            ELSE                          CASE WHEN b.deep_focus_min >  p.sem_focus_defaut_min THEN 1 ELSE 0 END
        END                                                                                        AS ok_deep_focus,
        CASE WHEN b.focus_projets_fond_min >= p.sem_projets_fond_min                THEN 1 ELSE 0 END AS ok_projets_fond,
        CASE WHEN b.focus_engagement_min >= p.sem_engagement_min
                  OR b.jours_engagement_semaine >= p.sem_engagement_jours           THEN 1 ELSE 0 END AS ok_engagement,
        CASE WHEN b.social = 'Connecté/Ressourcé' AND b.has_narrative               THEN 1 ELSE 0 END AS ok_cloture
    FROM base b
    CROSS JOIN v_score_params p
    LEFT JOIN modes_config mc ON mc.code = b.mode_actif
)
-- score final 0-100 : moyenne pondérée des critères (poids 0 = critère désactivé)
SELECT
    c.*,
    ROUND(100.0 * (
        c.ok_entrainement * p.poids_entrainement + c.ok_seances * p.poids_seances
        + c.ok_pas * p.poids_pas + c.ok_sommeil * p.poids_sommeil
        + c.ok_charge_fraicheur * p.poids_charge_fraicheur + c.ok_ecran * p.poids_ecran
        + c.ok_deep_focus * p.poids_deep_focus + c.ok_projets_fond * p.poids_projets_fond
        + c.ok_engagement * p.poids_engagement + c.ok_cloture * p.poids_cloture
    ) / NULLIF(
        p.poids_entrainement + p.poids_seances + p.poids_pas + p.poids_sommeil
        + p.poids_charge_fraicheur + p.poids_ecran + p.poids_deep_focus + p.poids_projets_fond
        + p.poids_engagement + p.poids_cloture, 0
    ), 1) AS score_semaine
FROM crit c
CROSS JOIN v_score_params p;

DROP VIEW IF EXISTS v_vigueur_hebdo;
CREATE VIEW v_vigueur_hebdo AS
SELECT
    sa.id,
    sa.week_start,
    sa.week_label,
    AVG(ve.ctl)              AS ctl_moy,
    AVG(ve.atl)              AS atl_moy,
    AVG(ve.tsb)              AS tsb_moy,
    SUM(ve.tss)              AS tss_total,
    MAX(ve.vo2max)           AS vo2max,
    SUM(ve.distance_km)      AS distance_km,
    SUM(ve.moving_time_min)  AS moving_time_min,
    AVG(ve.hrv)              AS hrv_moy,
    AVG(ve.rhr)              AS rhr_moy,
    AVG(ve.sleep_min)        AS sleep_moy,
    sa.screen_time_min,
    sa.deep_focus_min
FROM semaines_audit sa
LEFT JOIN vigueur_entries ve
    ON ve.date_entry >= sa.week_start
    AND ve.date_entry < date(sa.week_start, '+7 days')
GROUP BY sa.id
ORDER BY sa.week_start DESC;

-- ─────────────────────────────────────────────────────────────────
-- RÉSONNANCE — Audits trimestriel & annuel
-- ─────────────────────────────────────────────────────────────────
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
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(saison, annee)
);

-- Audit Annuel de Clarté & d'Alignement Personnel (Deci & Ryan / ACT).
-- theme1..4/conclusion : archive de l'ancien protocole (16 lois, Napoleon Hill).
CREATE TABLE IF NOT EXISTS audit_annuel (
    id          INTEGER PRIMARY KEY,
    annee       INTEGER NOT NULL UNIQUE,
    date_audit  TEXT,
    theme1      TEXT,
    theme2      TEXT,
    theme3      TEXT,
    theme4      TEXT,
    conclusion  TEXT,
    -- Module 1 — Socle Somatique & Régulation Nerveuse
    m1_note_recuperation       INTEGER,
    m1_note_signaux            INTEGER,
    m1_note_soupapes           INTEGER,
    m1_note_respiration        INTEGER,
    m1_cout_allostasie         TEXT,
    m1_sources_ressourcement   TEXT,
    -- Module 2 — Clarté Intrinsèque & Dynamique du Flow
    m2_note_flow               INTEGER,
    m2_note_fierte             INTEGER,
    m2_note_effort             INTEGER,
    m2_note_priorites          INTEGER,
    m2_flow_moment1            TEXT,
    m2_flow_moment2            TEXT,
    m2_friction_tache1         TEXT,
    m2_friction_tache2         TEXT,
    -- Module 3 — Écologie Relationnelle & Frontières Psychologiques
    m3_note_securite           INTEGER,
    m3_note_limites            INTEGER,
    m3_note_etancheite         INTEGER,
    m3_note_mutualite          INTEGER,
    m3_oui_complaisance1       TEXT,
    m3_oui_complaisance2       TEXT,
    m3_arbitrage_nourrir       TEXT,
    m3_arbitrage_reguler       TEXT,
    -- Module 4 — Flexibilité Cognitive & Traitement de l'Échec
    m4_note_locus              INTEGER,
    m4_note_autocompassion     INTEGER,
    m4_note_courage            INTEGER,
    m4_note_plasticite         INTEGER,
    m4_fait_brut               TEXT,
    m4_interpretation_initiale TEXT,
    m4_variable_controle       TEXT,
    m4_regle_systemique        TEXT,
    -- Module 5 — Feuille de Route & Intentions d'Implémentation
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
    -- Synthèse — objectifs pour l'année suivante (/20 par module)
    objectif_m1 INTEGER,
    objectif_m2 INTEGER,
    objectif_m3 INTEGER,
    objectif_m4 INTEGER,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ─────────────────────────────────────────────────────────────────
-- RÉSONNANCE — Notes pour trop tard
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS npt_personnes (
    id          INTEGER PRIMARY KEY,
    prenom      TEXT    NOT NULL,
    nom         TEXT    NOT NULL DEFAULT '',
    liens       TEXT    NOT NULL DEFAULT '',  -- comma-separated: "Famille,Amis"
    etat        TEXT    NOT NULL DEFAULT 'En vie et proche'
                        CHECK (etat IN ('En vie et proche', 'En vie et distant', 'Mort')),
    proximite   INTEGER,                      -- 0–100
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS npt_notes (
    id          INTEGER PRIMARY KEY,
    personne_id INTEGER NOT NULL REFERENCES npt_personnes(id) ON DELETE CASCADE,
    date_note   TEXT,                         -- ISO "2026-05-23", NULL si non daté
    contenu     TEXT    NOT NULL,
    source      TEXT    NOT NULL DEFAULT 'manual'
                        CHECK (source IN ('manual')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_npt_notes_personne ON npt_notes(personne_id, date_note DESC);

CREATE VIEW IF NOT EXISTS v_net_worth_actuel AS
SELECT
    c.source, c.libelle, c.classe_actif,
    sc.solde, sc.date_snapshot
FROM soldes_comptes sc
JOIN comptes c ON sc.compte_id = c.id
WHERE sc.date_snapshot = (
    SELECT MAX(date_snapshot) FROM soldes_comptes sc2
    WHERE sc2.compte_id = sc.compte_id
) AND c.actif = 1;

-- ─────────────────────────────────────────────
-- WORKOUT TRACKING
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exercise_library (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    category     TEXT,
    note         TEXT,
    load_formula TEXT    NOT NULL DEFAULT 'weight'
    -- 'weight'        : charge = poids utilisé
    -- 'bw_plus_weight': charge = poids du corps + lest (tractions, dips)
);

CREATE TABLE IF NOT EXISTS workout_templates (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS workout_template_exercises (
    id               INTEGER PRIMARY KEY,
    template_id      INTEGER NOT NULL REFERENCES workout_templates(id) ON DELETE CASCADE,
    exercise_id      INTEGER NOT NULL REFERENCES exercise_library(id),
    position         INTEGER NOT NULL,
    emom_interval_sec INTEGER,   -- NULL = pas EMOM ; 60 = une série par minute
    UNIQUE(template_id, position)
);

CREATE TABLE IF NOT EXISTS workout_template_sets (
    id               INTEGER PRIMARY KEY,
    tmpl_exercise_id INTEGER NOT NULL REFERENCES workout_template_exercises(id) ON DELETE CASCADE,
    set_index        INTEGER NOT NULL,
    set_type         TEXT    NOT NULL,   -- 'W', 'F', '1', '2', ...
    weight_kg        REAL    NOT NULL DEFAULT 0,
    reps             INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS workout_sessions (
    id                    INTEGER PRIMARY KEY,
    date_entry            TEXT    NOT NULL,
    template_id           INTEGER REFERENCES workout_templates(id),
    name                  TEXT    NOT NULL,
    started_at            TEXT,
    finished_at           TEXT,
    note                  TEXT,
    bodyweight_kg         REAL,
    session_volume_kg     REAL,
    intervals_activity_id TEXT    UNIQUE  -- FK logique vers l'activité Intervals.icu
);
CREATE INDEX IF NOT EXISTS idx_ws_date ON workout_sessions(date_entry DESC);

CREATE TABLE IF NOT EXISTS workout_session_exercises (
    id                INTEGER PRIMARY KEY,
    session_id        INTEGER NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
    exercise_id       INTEGER NOT NULL REFERENCES exercise_library(id),
    position          INTEGER NOT NULL,
    emom_interval_sec INTEGER
);

CREATE TABLE IF NOT EXISTS workout_session_sets (
    id            INTEGER PRIMARY KEY,
    session_ex_id INTEGER NOT NULL REFERENCES workout_session_exercises(id) ON DELETE CASCADE,
    set_index     INTEGER NOT NULL,
    set_type      TEXT    NOT NULL,   -- 'W', 'F', '1', '2', ...
    weight_kg     REAL    NOT NULL DEFAULT 0,
    reps          INTEGER NOT NULL DEFAULT 1,
    completed     INTEGER NOT NULL DEFAULT 0,
    load_kg       REAL,
    logged_at     TEXT    DEFAULT (datetime('now', 'localtime'))
);

CREATE VIEW IF NOT EXISTS v_habitudes_hebdo AS
SELECT
    sa.id,
    sa.week_start,
    COUNT(hl.id)               AS jours_loggues,
    SUM(hl.lecture_10min)      AS lecture_ok,
    SUM(hl.jeune_intermittent) AS jeune_ok,
    ROUND(100.0 * (
        COALESCE(SUM(hl.lecture_10min), 0) +
        COALESCE(SUM(hl.jeune_intermittent), 0)
    ) / (2.0 * NULLIF(COUNT(hl.id), 0)), 1) AS taux_global_pct
FROM semaines_audit sa
LEFT JOIN habitude_logs hl ON hl.semaine_id = sa.id
GROUP BY sa.id
ORDER BY sa.week_start DESC;

-- PILIER VIGUEUR — Prédiction de performance (Modèle Riegel)

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

-- Strava OAuth tokens (une seule ligne, id=1)
CREATE TABLE IF NOT EXISTS strava_oauth_tokens (
    id               INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    access_token     TEXT    NOT NULL,
    refresh_token    TEXT    NOT NULL,
    expires_at       INTEGER NOT NULL,   -- Unix epoch
    last_pr_sync_epoch INTEGER           -- Epoch du dernier sync Personal Records
);

-- Contenu de profil (textes, plans, référentiels personnels) : stocké en base, jamais dans le code.
CREATE TABLE IF NOT EXISTS profil_contenu (
    cle         TEXT PRIMARY KEY,
    valeur_json TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Applications comptées comme « écran distraction » (renseignées par l'utilisateur).
CREATE TABLE IF NOT EXISTS apps_distrayantes (
    package TEXT PRIMARY KEY
);

-- Suivi de projets : projet → phases (ordonnées) → tâches à cocher.
-- La phase courante d'un projet est la première phase (par ordre) qui a encore des tâches à valider.
CREATE TABLE IF NOT EXISTS projets (
    id          INTEGER PRIMARY KEY,
    titre       TEXT    NOT NULL,
    description TEXT,
    statut      TEXT    NOT NULL DEFAULT 'en_cours'
                 CHECK (statut IN ('en_cours','en_pause','termine','abandonne')),
    objectif_id INTEGER REFERENCES objectifs(id),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS projet_phases (
    id              INTEGER PRIMARY KEY,
    projet_id       INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    ordre           INTEGER NOT NULL DEFAULT 0,
    titre           TEXT    NOT NULL,
    objectif        TEXT,
    prochaine_etape TEXT,
    notes_json      TEXT,   -- [[titre, corps], ...]
    UNIQUE (projet_id, ordre)
);

CREATE TABLE IF NOT EXISTS projet_taches (
    id       INTEGER PRIMARY KEY,
    phase_id INTEGER NOT NULL REFERENCES projet_phases(id) ON DELETE CASCADE,
    ordre    INTEGER NOT NULL DEFAULT 0,
    libelle  TEXT    NOT NULL,
    fait     INTEGER NOT NULL DEFAULT 0 CHECK (fait IN (0, 1)),
    done_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_projets_statut ON projets(statut);
CREATE INDEX IF NOT EXISTS idx_projet_phases_projet ON projet_phases(projet_id, ordre);
CREATE INDEX IF NOT EXISTS idx_projet_taches_phase ON projet_taches(phase_id, fait);

-- ─────────────────────────────────────────────────────────────────
-- CONFIGURATION DU SCORE — recopiée depuis config/user.toml à chaque init_db()
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS score_config (
    cle    TEXT PRIMARY KEY,
    valeur REAL NOT NULL
);

-- Modes (séquences école / entreprise…) : libellé et seuils de focus par mode.
CREATE TABLE IF NOT EXISTS modes_config (
    code              TEXT PRIMARY KEY,
    libelle           TEXT NOT NULL,
    focus_jour_min    REAL NOT NULL,
    focus_semaine_min REAL NOT NULL,
    tag_pro           INTEGER NOT NULL DEFAULT 0,
    ordre             INTEGER NOT NULL DEFAULT 0
);

-- Une seule ligne : un paramètre par colonne (lue par v_score_semaine / v_progression_quotidienne).
DROP VIEW IF EXISTS v_score_params;
CREATE VIEW v_score_params AS
SELECT
    MAX(CASE WHEN cle = 'jour_sport_min' THEN valeur END) AS jour_sport_min,
    MAX(CASE WHEN cle = 'jour_sommeil_min' THEN valeur END) AS jour_sommeil_min,
    MAX(CASE WHEN cle = 'jour_pas' THEN valeur END) AS jour_pas,
    MAX(CASE WHEN cle = 'jour_focus_strat_min' THEN valeur END) AS jour_focus_strat_min,
    MAX(CASE WHEN cle = 'jour_ecran_max_min' THEN valeur END) AS jour_ecran_max_min,
    MAX(CASE WHEN cle = 'jour_focus_defaut_min' THEN valeur END) AS jour_focus_defaut_min,
    MAX(CASE WHEN cle = 'sem_seance_duree_min' THEN valeur END) AS sem_seance_duree_min,
    MAX(CASE WHEN cle = 'sem_entrainement_min' THEN valeur END) AS sem_entrainement_min,
    MAX(CASE WHEN cle = 'sem_seances' THEN valeur END) AS sem_seances,
    MAX(CASE WHEN cle = 'sem_pas' THEN valeur END) AS sem_pas,
    MAX(CASE WHEN cle = 'sem_sommeil_min' THEN valeur END) AS sem_sommeil_min,
    MAX(CASE WHEN cle = 'sem_tsb_min' THEN valeur END) AS sem_tsb_min,
    MAX(CASE WHEN cle = 'sem_tsb_decharge_min' THEN valeur END) AS sem_tsb_decharge_min,
    MAX(CASE WHEN cle = 'sem_ecran_max_min' THEN valeur END) AS sem_ecran_max_min,
    MAX(CASE WHEN cle = 'sem_projets_fond_min' THEN valeur END) AS sem_projets_fond_min,
    MAX(CASE WHEN cle = 'sem_engagement_min' THEN valeur END) AS sem_engagement_min,
    MAX(CASE WHEN cle = 'sem_engagement_jours' THEN valeur END) AS sem_engagement_jours,
    MAX(CASE WHEN cle = 'sem_focus_defaut_min' THEN valeur END) AS sem_focus_defaut_min,
    MAX(CASE WHEN cle = 'poids_entrainement' THEN valeur END) AS poids_entrainement,
    MAX(CASE WHEN cle = 'poids_seances' THEN valeur END) AS poids_seances,
    MAX(CASE WHEN cle = 'poids_pas' THEN valeur END) AS poids_pas,
    MAX(CASE WHEN cle = 'poids_sommeil' THEN valeur END) AS poids_sommeil,
    MAX(CASE WHEN cle = 'poids_charge_fraicheur' THEN valeur END) AS poids_charge_fraicheur,
    MAX(CASE WHEN cle = 'poids_ecran' THEN valeur END) AS poids_ecran,
    MAX(CASE WHEN cle = 'poids_deep_focus' THEN valeur END) AS poids_deep_focus,
    MAX(CASE WHEN cle = 'poids_projets_fond' THEN valeur END) AS poids_projets_fond,
    MAX(CASE WHEN cle = 'poids_engagement' THEN valeur END) AS poids_engagement,
    MAX(CASE WHEN cle = 'poids_cloture' THEN valeur END) AS poids_cloture
FROM score_config;
