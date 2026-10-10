-- Statut par source de synchronisation (page Système) : dernière réussite, dernière erreur, durée.
CREATE TABLE IF NOT EXISTS sync_checkpoints (
    source      TEXT PRIMARY KEY,
    last_date   TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
ALTER TABLE sync_checkpoints ADD COLUMN statut TEXT;
ALTER TABLE sync_checkpoints ADD COLUMN last_success_at TEXT;
ALTER TABLE sync_checkpoints ADD COLUMN last_error_at TEXT;
ALTER TABLE sync_checkpoints ADD COLUMN last_error TEXT;
ALTER TABLE sync_checkpoints ADD COLUMN last_duration_s REAL;
