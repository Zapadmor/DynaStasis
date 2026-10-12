"""Requêtes sur les tables `projets`, `projet_phases` et `projet_taches`."""

from __future__ import annotations

import json
import sqlite3


def liste_par_statut(conn: sqlite3.Connection, statut: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM projets WHERE statut = ? ORDER BY created_at, id", (statut,)
        )
    ]


def progression(conn: sqlite3.Connection, projet_id: int) -> tuple[int, int]:
    """(tâches au total, tâches faites) d'un projet."""
    total, faites = conn.execute(
        """SELECT COUNT(t.id), COALESCE(SUM(t.fait), 0)
           FROM projet_taches t JOIN projet_phases ph ON ph.id = t.phase_id
           WHERE ph.projet_id = ?""",
        (projet_id,),
    ).fetchone()
    return total, faites


def phase_courante(conn: sqlite3.Connection, projet_id: int) -> dict | None:
    """Première phase (par `ordre`) qui compte encore au moins une tâche non cochée."""
    row = conn.execute(
        """
        SELECT ph.*
        FROM projet_phases ph
        WHERE ph.projet_id = ?
          AND EXISTS (SELECT 1 FROM projet_taches t WHERE t.phase_id = ph.id AND t.fait = 0)
        ORDER BY ph.ordre, ph.id
        LIMIT 1
        """,
        (projet_id,),
    ).fetchone()
    if row is None:
        return None
    phase = dict(row)
    phase["notes"] = json.loads(row["notes_json"] or "[]")
    return phase


def taches_de_phase(conn: sqlite3.Connection, phase_id: int) -> list[dict]:
    return [
        dict(t)
        for t in conn.execute(
            "SELECT id, libelle, fait FROM projet_taches WHERE phase_id = ? ORDER BY ordre, id",
            (phase_id,),
        )
    ]


def phases_avec_progression(conn: sqlite3.Connection, projet_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT ph.id, ph.titre,
                      COUNT(t.id) AS total, COALESCE(SUM(t.fait), 0) AS faites
               FROM projet_phases ph LEFT JOIN projet_taches t ON t.phase_id = ph.id
               WHERE ph.projet_id = ? GROUP BY ph.id ORDER BY ph.ordre, ph.id""",
            (projet_id,),
        )
    ]


def cocher_tache(conn: sqlite3.Connection, tache_id: int, fait: bool) -> None:
    conn.execute(
        "UPDATE projet_taches SET fait = ?, "
        "done_at = CASE WHEN ? THEN datetime('now', 'localtime') END WHERE id = ?",
        (int(fait), int(fait), tache_id),
    )
    conn.execute(
        "UPDATE projets SET updated_at = datetime('now', 'localtime') WHERE id = "
        "(SELECT ph.projet_id FROM projet_taches t JOIN projet_phases ph ON ph.id = t.phase_id "
        "WHERE t.id = ?)",
        (tache_id,),
    )


def inserer_projet(
    conn: sqlite3.Connection, titre: str, description: str | None, objectif_id: int | None
) -> int:
    cur = conn.execute(
        "INSERT INTO projets (titre, description, objectif_id) VALUES (?, ?, ?)",
        (titre, description, objectif_id),
    )
    return int(cur.lastrowid)


def inserer_phase(
    conn: sqlite3.Connection,
    projet_id: int,
    titre: str,
    objectif: str | None,
    prochaine_etape: str | None,
    notes: list[tuple[str, str]] | None,
) -> int:
    """Ajoute la phase en dernière position du projet."""
    ordre = conn.execute(
        "SELECT COALESCE(MAX(ordre), 0) + 1 FROM projet_phases WHERE projet_id = ?",
        (projet_id,),
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO projet_phases (projet_id, ordre, titre, objectif, prochaine_etape, "
        "notes_json) VALUES (?, ?, ?, ?, ?, ?)",
        (
            projet_id,
            ordre,
            titre,
            objectif,
            prochaine_etape,
            json.dumps(notes, ensure_ascii=False) if notes else None,
        ),
    )
    return int(cur.lastrowid)


def inserer_tache(conn: sqlite3.Connection, phase_id: int, libelle: str, fait: bool) -> int:
    """Ajoute la tâche en dernière position de la phase."""
    ordre = conn.execute(
        "SELECT COALESCE(MAX(ordre), 0) + 1 FROM projet_taches WHERE phase_id = ?",
        (phase_id,),
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO projet_taches (phase_id, ordre, libelle, fait) VALUES (?, ?, ?, ?)",
        (phase_id, ordre, libelle, int(fait)),
    )
    return int(cur.lastrowid)


def maj_statut(conn: sqlite3.Connection, projet_id: int, statut: str) -> None:
    conn.execute(
        "UPDATE projets SET statut = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (statut, projet_id),
    )


def gerables(conn: sqlite3.Connection) -> list[dict]:
    """Projets modifiables (en cours ou en pause)."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id, titre, statut FROM projets "
            "WHERE statut IN ('en_cours', 'en_pause') ORDER BY titre"
        )
    ]


def phases_gerables(conn: sqlite3.Connection) -> list[dict]:
    """Phases des projets modifiables, avec le titre du projet."""
    return [
        dict(r)
        for r in conn.execute(
            """SELECT ph.id, ph.titre AS phase, p.titre AS projet
               FROM projet_phases ph JOIN projets p ON p.id = ph.projet_id
               WHERE p.statut IN ('en_cours', 'en_pause')
               ORDER BY p.titre, ph.ordre, ph.id"""
        )
    ]
