from __future__ import annotations

import importlib.util
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.core import user_config

# Base par défaut ; `DYNASTASIS_DB` permet d'en utiliser une autre (ex. base de démo).
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "db" / "dynastasie.db"
DB_PATH = Path(os.environ.get("DYNASTASIS_DB") or DEFAULT_DB_PATH)
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


# Erreurs SQLite qui signalent une migration déjà appliquée (rejeu d'un ALTER)
_IDEMPOTENT_ERRORS = ("duplicate column name", "no such column")


def _migration_files() -> list[tuple[int, Path]]:
    """Migrations `NNN_description.sql` (ou `.py` avec une fonction `apply(conn)`) triées par numéro."""
    files = []
    for path in [*MIGRATIONS_DIR.glob("*.sql"), *MIGRATIONS_DIR.glob("*.py")]:
        prefix = path.name.split("_", 1)[0]
        if prefix.isdigit():
            files.append((int(prefix), path))
    return sorted(files)


def latest_version() -> int:
    """Numéro de la dernière migration disponible."""
    files = _migration_files()
    return files[-1][0] if files else 0


def _apply_python_migration(conn: sqlite3.Connection, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.apply(conn)


def _apply_migration(conn: sqlite3.Connection, path: Path) -> None:
    """Exécute un fichier instruction par instruction ; ignore les ALTER déjà appliqués."""
    if path.suffix == ".py":
        _apply_python_migration(conn, path)
        return
    buffer = ""
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        buffer += line
        if not sqlite3.complete_statement(buffer):
            continue
        statement, buffer = buffer.strip(), ""
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if not any(msg in str(exc) for msg in _IDEMPOTENT_ERRORS):
                raise


def _drop_views(conn: sqlite3.Connection) -> None:
    """Supprime les vues : un RENAME COLUMN échoue si une vue référence une colonne manquante.
    `schema.sql` les recrée après les migrations."""
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'").fetchall():
        conn.execute(f'DROP VIEW IF EXISTS "{name}"')


def _run_migrations(conn: sqlite3.Connection) -> bool:
    """Applique les migrations dont le numéro dépasse `PRAGMA user_version`.
    Retourne True si au moins une migration a été appliquée."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    pending = [(v, p) for v, p in _migration_files() if v > current]
    if not pending:
        return False
    _drop_views(conn)
    conn.commit()
    # Reconstruire une table impose de suspendre les clés étrangères (hors transaction).
    conn.execute("PRAGMA foreign_keys = OFF;")
    avant = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    try:
        for version, path in pending:
            _apply_migration(conn, path)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        # des orphelins antérieurs aux migrations sont tolérés ; une migration ne doit pas en créer
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if len(violations) > avant:
            raise sqlite3.IntegrityError(
                f"Clés étrangères violées par la migration : {violations[:5]}"
            )
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")
    return True


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
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)
        if _run_migrations(conn):
            conn.executescript(schema)  # recrée les vues supprimées pendant les migrations
        _drop_legacy_notion(conn)
        user_config.sync_to_db(conn)
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
