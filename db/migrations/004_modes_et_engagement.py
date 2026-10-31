"""Modes et critère « engagement » génériques.

- les deux modes d'origine deviennent des codes configurables (config/user.toml, `[modes.*]`) :
  levée des CHECK sur `semaines_audit.mode_actif` et `sequences_mode.lieu`, puis conversion
  des anciennes valeurs vers les codes de la configuration ;
- le critère propre à l'auteur devient « engagement » : tag `FORGE_ENGAGEMENT` → `FORGE_ENGAGEMENT`,
  colonnes `*_engagement*` / `jours_engagement_semaine` renommées.

Idempotent : chaque étape ne fait rien si elle est déjà appliquée.
"""

from __future__ import annotations

import re
import sqlite3

RENAMES = [
    ("semaines_audit", "focus_engagement_min", "focus_engagement_min"),
    ("audit_narrative", "forge_jours_engagement_mois", "forge_jours_engagement_mois"),
    ("audit_narrative", "jours_engagement_semaine", "jours_engagement_semaine"),
    ("audit_narrative", "forge_drill_engagement", "forge_drill_engagement"),
    ("audit_narrative", "plan_drill_engagement", "plan_drill_engagement"),
]


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _rename_columns(conn: sqlite3.Connection) -> None:
    for table, old, new in RENAMES:
        cols = _columns(conn, table)
        if old in cols and new not in cols:
            conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
        elif old in cols and new in cols:
            # rejeu de 002 après un renommage : ré-ajoute l'ancienne colonne, vide
            conn.execute(f"UPDATE {table} SET {new} = COALESCE({new}, {old})")
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {old}")


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
    _rename_columns(conn)
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
    for table in ("focus_sessions", "system_freezes"):
        if "piliers" in _columns(conn, table):
            conn.execute(
                f"UPDATE {table} SET piliers = replace(piliers, 'FORGE_ENGAGEMENT', 'FORGE_ENGAGEMENT') "
                "WHERE piliers LIKE '%FORGE_ENGAGEMENT%'"
            )
