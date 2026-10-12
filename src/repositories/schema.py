"""Introspection du schéma SQLite."""

from __future__ import annotations

import sqlite3


def table_existe(conn: sqlite3.Connection, nom: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (nom,)
        ).fetchone()
        is not None
    )
