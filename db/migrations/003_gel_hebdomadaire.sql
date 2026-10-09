-- Gel hebdomadaire : périodes de gel et drapeau par semaine.
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

ALTER TABLE semaines_audit ADD COLUMN is_frozen INTEGER NOT NULL DEFAULT 0;
