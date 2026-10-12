"""Requêtes sur les objectifs et leurs tâches."""

from __future__ import annotations

import sqlite3


def actifs(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM objectifs WHERE statut != 'abandonne' ORDER BY priorite, created_at"
        )
    ]


def taches(conn: sqlite3.Connection, objectif_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM taches WHERE objectif_id=? AND statut != 'annule' "
            "ORDER BY priorite, created_at",
            (objectif_id,),
        )
    ]


def inserer(
    conn: sqlite3.Connection,
    titre: str,
    pilier: str,
    date_cible: str | None,
    description: str | None,
    priorite: int,
) -> None:
    conn.execute(
        "INSERT INTO objectifs (titre, pilier, date_cible, description, priorite) "
        "VALUES (?,?,?,?,?)",
        (titre, pilier, date_cible, description, priorite),
    )


def archiver(conn: sqlite3.Connection, objectif_id: int) -> None:
    conn.execute(
        "UPDATE objectifs SET statut='abandonne', updated_at=datetime('now') WHERE id=?",
        (objectif_id,),
    )


def inserer_tache(
    conn: sqlite3.Connection,
    objectif_id: int,
    titre: str,
    priorite: int,
    date_echeance: str | None,
) -> None:
    conn.execute(
        "INSERT INTO taches (titre, objectif_id, priorite, date_echeance) VALUES (?,?,?,?)",
        (titre, objectif_id, priorite, date_echeance),
    )


def maj_statut_tache(conn: sqlite3.Connection, tache_id: int, fait: bool) -> None:
    if fait:
        conn.execute(
            "UPDATE taches SET statut='fait', completed_at=datetime('now') WHERE id=?",
            (tache_id,),
        )
    else:
        conn.execute("UPDATE taches SET statut='todo', completed_at=NULL WHERE id=?", (tache_id,))


def annuler_tache(conn: sqlite3.Connection, tache_id: int) -> None:
    conn.execute("UPDATE taches SET statut='annule' WHERE id=?", (tache_id,))
