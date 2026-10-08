"""Suivi de projets : projet → phases ordonnées → tâches à cocher (tables projets*).

La phase courante d'un projet est la première phase (par `ordre`) qui compte encore au moins
une tâche non cochée. Les phases sans tâche sont ignorées pour ce calcul.
"""

from __future__ import annotations

import json
import sqlite3

from src.database.connection import db_session

STATUTS = ("en_cours", "en_pause", "termine", "abandonne")


def _phase_courante(conn: sqlite3.Connection, projet_id: int) -> sqlite3.Row | None:
    return conn.execute(
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


def projets_en_cours() -> list[dict]:
    """Projets au statut « en_cours », avec progression et phase courante (tâches incluses)."""
    result: list[dict] = []
    with db_session() as conn:
        for projet in conn.execute(
            "SELECT * FROM projets WHERE statut = 'en_cours' ORDER BY created_at, id"
        ).fetchall():
            total, faites = conn.execute(
                """SELECT COUNT(t.id), COALESCE(SUM(t.fait), 0)
                   FROM projet_taches t JOIN projet_phases ph ON ph.id = t.phase_id
                   WHERE ph.projet_id = ?""",
                (projet["id"],),
            ).fetchone()
            phase = _phase_courante(conn, projet["id"])
            phase_dict = None
            if phase is not None:
                phase_dict = dict(phase)
                phase_dict["notes"] = json.loads(phase["notes_json"] or "[]")
                phase_dict["taches"] = [
                    dict(t)
                    for t in conn.execute(
                        "SELECT id, libelle, fait FROM projet_taches "
                        "WHERE phase_id = ? ORDER BY ordre, id",
                        (phase["id"],),
                    ).fetchall()
                ]
            phases = [
                dict(r)
                for r in conn.execute(
                    """SELECT ph.id, ph.titre,
                              COUNT(t.id) AS total, COALESCE(SUM(t.fait), 0) AS faites
                       FROM projet_phases ph LEFT JOIN projet_taches t ON t.phase_id = ph.id
                       WHERE ph.projet_id = ? GROUP BY ph.id ORDER BY ph.ordre, ph.id""",
                    (projet["id"],),
                ).fetchall()
            ]
            result.append(
                {
                    **dict(projet),
                    "total": total,
                    "faites": faites,
                    "phase": phase_dict,
                    "phases": phases,
                }
            )
    return result


def set_tache(tache_id: int, fait: bool) -> None:
    with db_session() as conn:
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


def creer_projet(titre: str, description: str | None = None, objectif_id: int | None = None) -> int:
    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO projets (titre, description, objectif_id) VALUES (?, ?, ?)",
            (titre, description or None, objectif_id),
        )
        return int(cur.lastrowid)


def ajouter_phase(
    projet_id: int,
    titre: str,
    objectif: str | None = None,
    prochaine_etape: str | None = None,
    notes: list[tuple[str, str]] | None = None,
) -> int:
    with db_session() as conn:
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
                objectif or None,
                prochaine_etape or None,
                json.dumps(notes, ensure_ascii=False) if notes else None,
            ),
        )
        return int(cur.lastrowid)


def ajouter_tache(phase_id: int, libelle: str, fait: bool = False) -> int:
    with db_session() as conn:
        ordre = conn.execute(
            "SELECT COALESCE(MAX(ordre), 0) + 1 FROM projet_taches WHERE phase_id = ?",
            (phase_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO projet_taches (phase_id, ordre, libelle, fait) VALUES (?, ?, ?, ?)",
            (phase_id, ordre, libelle, int(fait)),
        )
        return int(cur.lastrowid)


def changer_statut(projet_id: int, statut: str) -> None:
    if statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {statut}")
    with db_session() as conn:
        conn.execute(
            "UPDATE projets SET statut = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (statut, projet_id),
        )


def projets_gerables() -> list[dict]:
    """Projets modifiables (en cours ou en pause)."""
    with db_session() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, titre, statut FROM projets "
                "WHERE statut IN ('en_cours', 'en_pause') ORDER BY titre"
            ).fetchall()
        ]


def phases_gerables() -> list[dict]:
    """Phases des projets modifiables, avec le titre du projet (pour ajouter des tâches)."""
    with db_session() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """SELECT ph.id, ph.titre AS phase, p.titre AS projet
                   FROM projet_phases ph JOIN projets p ON p.id = ph.projet_id
                   WHERE p.statut IN ('en_cours', 'en_pause')
                   ORDER BY p.titre, ph.ordre, ph.id"""
            ).fetchall()
        ]
