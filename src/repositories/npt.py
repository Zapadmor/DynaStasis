"""Requêtes sur les « notes pour trop tard » (`npt_personnes`, `npt_notes`)."""

from __future__ import annotations

import sqlite3

from src.repositories.schema import table_existe


def tables_pretes(conn: sqlite3.Connection) -> bool:
    return table_existe(conn, "npt_personnes") and table_existe(conn, "npt_notes")


def personnes(conn: sqlite3.Connection) -> list[dict]:
    """Proches, d'abord les vivants et proches, puis par proximité décroissante."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM npt_personnes ORDER BY "
            "CASE etat WHEN 'En vie et proche' THEN 0 WHEN 'Mort' THEN 1 ELSE 2 END, "
            "COALESCE(proximite, 0) DESC"
        )
    ]


def notes(conn: sqlite3.Connection, personne_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM npt_notes WHERE personne_id=? ORDER BY date_note DESC, id DESC",
            (personne_id,),
        )
    ]


def ajouter_note(conn: sqlite3.Connection, personne_id: int, date_note: str, contenu: str) -> None:
    conn.execute(
        "INSERT INTO npt_notes (personne_id, date_note, contenu) VALUES (?,?,?)",
        (personne_id, date_note, contenu),
    )


def ajouter_personne(
    conn: sqlite3.Connection,
    prenom: str,
    nom: str,
    liens: list[str],
    etat: str,
    proximite: int | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO npt_personnes (prenom, nom, liens, etat, proximite) VALUES (?,?,?,?,?)",
        (prenom, nom, ",".join(liens), etat, proximite),
    )
    return cur.lastrowid
