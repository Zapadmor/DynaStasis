"""Requêtes sur `semaines_audit` et les tables/vues qui l'alimentent (cascade hebdomadaire)."""

from __future__ import annotations

import sqlite3


def id_par_debut(conn: sqlite3.Connection, week_start: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM semaines_audit WHERE week_start = ?", (week_start,)
    ).fetchone()
    return row["id"] if row else None


def mode_planifie(conn: sqlite3.Connection, week_start: str) -> str | None:
    """Mode de la séquence qui couvre le lundi donné (`sequences_mode`), s'il y en a une."""
    row = conn.execute(
        "SELECT lieu FROM sequences_mode WHERE ? BETWEEN date_debut AND date_fin",
        (week_start,),
    ).fetchone()
    return row["lieu"] if row else None


def est_gelee(conn: sqlite3.Connection, week_start: str) -> bool:
    """Vrai si une pause (`system_freezes`) chevauche la semaine commençant à `week_start`."""
    return (
        conn.execute(
            "SELECT 1 FROM system_freezes"
            " WHERE ? <= date_fin AND date(?, '+6 days') >= date_debut LIMIT 1",
            (week_start, week_start),
        ).fetchone()
        is not None
    )


def inserer(
    conn: sqlite3.Connection, week_start: str, week_label: str, mode_actif: str, is_frozen: bool
) -> int:
    cur = conn.execute(
        "INSERT INTO semaines_audit (week_start, week_label, mode_actif, is_frozen)"
        " VALUES (?, ?, ?, ?)",
        (week_start, week_label, mode_actif, int(is_frozen)),
    )
    return cur.lastrowid


def minutes_deep_focus(conn: sqlite3.Connection, week_id: int) -> float:
    row = conn.execute(
        "SELECT minutes_totales FROM v_deep_focus_hebdo WHERE semaine_id = ?", (week_id,)
    ).fetchone()
    return row["minutes_totales"] if row else 0.0


def totaux_habitudes(conn: sqlite3.Connection, week_id: int) -> dict:
    return dict(
        conn.execute(
            """SELECT
                COALESCE(SUM(bonne_recup_8h9h), 0)    AS recup,
                COALESCE(SUM(lecture_10min), 0)        AS lecture,
                COALESCE(SUM(sport_marche_45min), 0)   AS sport,
                COALESCE(SUM(jeune_intermittent), 0)   AS jeune
               FROM habitude_logs WHERE semaine_id = ?""",
            (week_id,),
        ).fetchone()
    )


def maj_cumuls(
    conn: sqlite3.Connection,
    week_id: int,
    *,
    deep_focus_min: float,
    habitudes: dict,
    focus_engagement_min: float,
    focus_projets_fond_min: float,
) -> None:
    conn.execute(
        """UPDATE semaines_audit SET
            deep_focus_min          = ?,
            nuits_bonne_recup       = ?,
            sessions_lecture        = ?,
            sessions_sport          = ?,
            sessions_jeune          = ?,
            focus_engagement_min    = ?,
            focus_projets_fond_min  = ?,
            updated_at              = datetime('now')
           WHERE id = ?""",
        (
            deep_focus_min,
            habitudes["recup"],
            habitudes["lecture"],
            habitudes["sport"],
            habitudes["jeune"],
            focus_engagement_min,
            focus_projets_fond_min,
            week_id,
        ),
    )


def score_calcule(conn: sqlite3.Connection, week_id: int) -> dict | None:
    """Score et moyennes HRV tels que la vue `v_score_semaine` les calcule."""
    row = conn.execute(
        "SELECT score_semaine, hrv_moy, hrv_moy_prev FROM v_score_semaine WHERE id = ?",
        (week_id,),
    ).fetchone()
    return dict(row) if row else None


def maj_score(
    conn: sqlite3.Connection, week_id: int, score: float | None, hrv_delta: float | None
) -> None:
    conn.execute(
        "UPDATE semaines_audit SET score_semaine = ?, hrv_delta_s1 = ? WHERE id = ?",
        (score, hrv_delta, week_id),
    )
