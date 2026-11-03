"""Requêtes sur les « notes pour trop tard » (`npt_personnes`, `npt_notes`, `npt_chantiers`)."""

from __future__ import annotations

import sqlite3

from src.repositories.schema import table_existe


def tables_pretes(conn: sqlite3.Connection) -> bool:
    return table_existe(conn, "npt_personnes") and table_existe(conn, "npt_notes")


def chantiers_prets(conn: sqlite3.Connection) -> bool:
    return table_existe(conn, "npt_chantiers") and table_existe(conn, "npt_chantier_entrees")


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


# ── Chantiers d'introspection ────────────────────────────────────────────────


def chantiers(conn: sqlite3.Connection) -> list[dict]:
    """Chantiers non clos d'abord, puis les plus récemment modifiés ; avec le nom de la personne."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT c.*, TRIM(COALESCE(p.prenom, '') || ' ' || COALESCE(p.nom, '')) AS personne, "
            "(SELECT COUNT(*) FROM npt_chantier_entrees e WHERE e.chantier_id = c.id) AS nb_entrees "
            "FROM npt_chantiers c LEFT JOIN npt_personnes p ON p.id = c.personne_id "
            "ORDER BY CASE c.statut WHEN 'En cours' THEN 0 WHEN 'Ouvert' THEN 1 ELSE 2 END, "
            "c.updated_at DESC, c.id DESC"
        )
    ]


def entrees(conn: sqlite3.Connection, chantier_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM npt_chantier_entrees WHERE chantier_id=? "
            "ORDER BY date_entree DESC, id DESC",
            (chantier_id,),
        )
    ]


def ajouter_chantier(
    conn: sqlite3.Connection,
    personne_id: int | None,
    type_: str,
    titre: str,
    description: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO npt_chantiers (personne_id, type, titre, description) VALUES (?,?,?,?)",
        (personne_id, type_, titre, description),
    )
    return cur.lastrowid


def changer_statut_chantier(conn: sqlite3.Connection, chantier_id: int, statut: str) -> None:
    conn.execute(
        "UPDATE npt_chantiers SET statut=?, updated_at=datetime('now','localtime') WHERE id=?",
        (statut, chantier_id),
    )


def ajouter_entree(
    conn: sqlite3.Connection, chantier_id: int, date_entree: str, contenu: str
) -> None:
    conn.execute(
        "INSERT INTO npt_chantier_entrees (chantier_id, date_entree, contenu) VALUES (?,?,?)",
        (chantier_id, date_entree, contenu),
    )
    conn.execute(
        "UPDATE npt_chantiers SET updated_at=datetime('now','localtime') WHERE id=?",
        (chantier_id,),
    )
