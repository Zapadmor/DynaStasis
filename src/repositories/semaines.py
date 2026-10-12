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


# ── Métriques consolidées de la semaine (onglet audit hebdo) ────────────────────────────────────


def debut(conn: sqlite3.Connection, week_id: int) -> str | None:
    row = conn.execute("SELECT week_start FROM semaines_audit WHERE id = ?", (week_id,)).fetchone()
    return row["week_start"] if row else None


def vigueur_hebdo(conn: sqlite3.Connection, week_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM v_vigueur_hebdo WHERE id = ?", (week_id,)).fetchone()
    return dict(row) if row else None


def ctl_moyen_precedent(conn: sqlite3.Connection, week_start: str) -> float | None:
    """CTL moyen de la dernière semaine non gelée avant `week_start`."""
    row = conn.execute(
        """SELECT AVG(ve.ctl) AS ctl_moy
           FROM semaines_audit sa
           JOIN vigueur_entries ve
             ON ve.date_entry >= sa.week_start
            AND ve.date_entry < date(sa.week_start, '+7 days')
           WHERE sa.week_start = (
             SELECT week_start FROM semaines_audit
             WHERE week_start < ? AND is_frozen = 0
             ORDER BY week_start DESC LIMIT 1
           )""",
        (week_start,),
    ).fetchone()
    return row["ctl_moy"] if row else None


def ecran_total_min(conn: sqlite3.Connection, week_start: str) -> float | None:
    row = conn.execute(
        """SELECT SUM(duration_seconds) / 60.0 AS total_min
           FROM screen_sessions
           WHERE session_start >= ? AND session_start < date(?, '+7 days')""",
        (week_start, week_start),
    ).fetchone()
    return row["total_min"] if row else None


def top_apps(conn: sqlite3.Connection, week_start: str, limite: int = 5) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT app_name, SUM(duration_seconds) / 60.0 AS fg_min
               FROM screen_sessions
               WHERE session_start >= ? AND session_start < date(?, '+7 days')
               GROUP BY app_name ORDER BY fg_min DESC LIMIT ?""",
            (week_start, week_start, limite),
        )
    ]


def maj_metriques(conn: sqlite3.Connection, week_id: int, m: dict) -> None:
    """Écrit les métriques Vigueur/écran ; l'écran n'écrase pas une valeur existante par NULL."""
    conn.execute(
        """UPDATE semaines_audit SET
               ctl             = ?,
               atl             = ?,
               tsb             = ?,
               tss             = ?,
               ctl_delta       = ?,
               vo2max          = ?,
               distance_km     = ?,
               temps_sport_min = ?,
               screen_time_min = COALESCE(?, screen_time_min),
               top_apps_text   = COALESCE(?, top_apps_text),
               updated_at      = datetime('now')
           WHERE id = ?""",
        (
            m["ctl"],
            m["atl"],
            m["tsb"],
            m["tss"],
            m["ctl_delta"],
            m["vo2max"],
            m["distance_km"],
            m["temps_sport_min"],
            m["screen_time_min"],
            m["top_apps_text"],
            week_id,
        ),
    )


def score_vue(conn: sqlite3.Connection, week_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM v_score_semaine WHERE id = ?", (week_id,)).fetchone()
    return dict(row) if row else None


def metriques(conn: sqlite3.Connection, week_id: int) -> dict | None:
    row = conn.execute(
        """SELECT ctl, atl, tsb, tss, ctl_delta, vo2max,
                  distance_km, temps_sport_min, screen_time_min,
                  top_apps_text, score_semaine
           FROM semaines_audit WHERE id = ?""",
        (week_id,),
    ).fetchone()
    return dict(row) if row else None


def vigueur_agregat(conn: sqlite3.Connection, week_start: str) -> dict | None:
    """Totaux et moyennes des entrées Vigueur de la semaine commençant à `week_start`."""
    row = conn.execute(
        """SELECT SUM(moving_time_min) AS moving_time_min, SUM(distance_km) AS distance_km,
                  AVG(hrv) AS hrv_moy, AVG(sleep_min) AS sleep_moy
           FROM vigueur_entries
           WHERE date_entry >= ? AND date_entry < date(?, '+7 days')""",
        (week_start, week_start),
    ).fetchone()
    return dict(row) if row else None


def ecran_distraction_min(conn: sqlite3.Connection, week_id: int) -> float | None:
    row = conn.execute(
        "SELECT screen_distraction_min FROM v_score_semaine WHERE id = ?", (week_id,)
    ).fetchone()
    return row["screen_distraction_min"] if row else None


def objectif_actif_id(conn: sqlite3.Connection, titre: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM objectifs WHERE titre = ? AND statut = 'actif'", (titre,)
    ).fetchone()
    return row["id"] if row else None


def taches_objectif(conn: sqlite3.Connection, objectif_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT statut, date_echeance FROM taches WHERE objectif_id = ?", (objectif_id,)
        )
    ]
