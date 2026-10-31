"""Modes génériques.

Les deux modes d'origine deviennent des codes configurables (config/user.toml, `[modes.*]`) :
levée des CHECK sur `semaines_audit.mode_actif` et `sequences_mode.lieu`, puis conversion
des anciennes valeurs vers les codes de la configuration.

Idempotent : chaque étape ne fait rien si elle est déjà appliquée.
"""

from __future__ import annotations

import re
import sqlite3


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _rebuild_without_check(conn: sqlite3.Connection, table: str, column: str) -> None:
    """Reconstruit la table sans le CHECK `column IN (...)` (procédure SQLite en 12 étapes ;
    les clés étrangères sont désactivées par le runner pendant la migration)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if row is None:
        return
    pattern = re.compile(rf"CHECK\s*\(\s*{column}\s+IN\s*\([^)]*\)\s*\)", re.IGNORECASE)
    if not pattern.search(row[0]):
        return
    new_sql = pattern.sub("", row[0], count=1)
    new_sql = re.sub(
        rf"CREATE TABLE\s+(IF NOT EXISTS\s+)?[\"`]?{table}[\"`]?",
        f"CREATE TABLE {table}__new",
        new_sql,
        count=1,
        flags=re.IGNORECASE,
    )
    indexes = [
        r[0]
        for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
            (table,),
        )
    ]
    conn.execute(new_sql)
    conn.execute(f"INSERT INTO {table}__new SELECT * FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
    for sql in indexes:
        conn.execute(sql)


def _legacy_mode_codes() -> tuple[str, str]:
    """Codes de la configuration qui reprennent les deux modes d'origine (non professionnel / professionnel)."""
    from src.core import user_config

    modes = list(user_config.modes().values())
    ecole = next((m.code for m in modes if not m.tag_pro), modes[0].code)
    entreprise = next((m.code for m in modes if m.tag_pro), modes[-1].code)
    return ecole, entreprise


def apply(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    _rebuild_without_check(conn, "semaines_audit", "mode_actif")
    _rebuild_without_check(conn, "sequences_mode", "lieu")

    ecole, entreprise = _legacy_mode_codes()
    for table, column in (("semaines_audit", "mode_actif"), ("sequences_mode", "lieu")):
        if column in _columns(conn, table):
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE {column} = 'Entreprise'", (entreprise,)
            )
            # toute autre valeur d'origine correspond au mode non professionnel
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE {column} NOT IN (?, ?)",
                (ecole, ecole, entreprise),
            )
