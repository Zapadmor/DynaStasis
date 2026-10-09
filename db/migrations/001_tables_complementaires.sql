-- Tables absentes de schema.sql, créées après coup (idempotent).
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
