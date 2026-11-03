-- Documents markdown (notes, rapports) : stockés en base, jamais dans l'historique git.
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    source      TEXT    NOT NULL UNIQUE,  -- chemin relatif au dossier importé (clé d'import)
    titre       TEXT    NOT NULL,
    categorie   TEXT    NOT NULL DEFAULT '',
    contenu_md  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_documents_categorie ON documents(categorie);
