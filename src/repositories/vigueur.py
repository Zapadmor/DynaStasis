"""Requêtes de la page Vigueur : charge d'entraînement, écran, séances."""

from __future__ import annotations

import sqlite3


def hebdo(conn: sqlite3.Connection, limite: int = 26) -> list[dict]:
    """Vue `v_vigueur_hebdo`, semaines les plus récentes d'abord."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM v_vigueur_hebdo ORDER BY week_start DESC LIMIT ?", (limite,)
        )
    ]


def derniers_jours(conn: sqlite3.Connection, n: int = 7) -> list[dict]:
    """Dernières entrées quotidiennes, la plus récente d'abord."""
    return [
        dict(r)
        for r in conn.execute(
            """SELECT date_entry, hrv, rhr, sleep_min, steps, ctl, atl, tsb
               FROM vigueur_entries ORDER BY date_entry DESC LIMIT ?""",
            (n,),
        )
    ]


def charge_quotidienne(conn: sqlite3.Connection) -> list[dict]:
    """CTL/ATL/TSB/TSS de tous les jours renseignés, du plus ancien au plus récent."""
    return [
        dict(r)
        for r in conn.execute(
            """SELECT date_entry, ctl, atl, tsb, tss
               FROM vigueur_entries WHERE ctl IS NOT NULL
               ORDER BY date_entry ASC"""
        )
    ]


def ecran_top_apps(conn: sqlite3.Connection, limite: int = 5) -> list[dict]:
    """Applications les plus utilisées sur les 7 derniers jours (minutes)."""
    return [
        dict(r)
        for r in conn.execute(
            """SELECT app_name, ROUND(SUM(duration_seconds) / 60.0, 1) AS minutes
               FROM screen_sessions
               WHERE session_start >= datetime('now', '-7 days')
               GROUP BY app_name
               ORDER BY minutes DESC
               LIMIT ?""",
            (limite,),
        )
    ]


def ecran_total_heures(conn: sqlite3.Connection) -> float | None:
    """Temps d'écran des 7 derniers jours, en heures."""
    row = conn.execute(
        """SELECT ROUND(SUM(duration_seconds) / 3600.0, 1)
           FROM screen_sessions
           WHERE session_start >= datetime('now', '-7 days')"""
    ).fetchone()
    return row[0] if row else None


def resume_seance(conn: sqlite3.Connection, session_id: int) -> dict | None:
    row = conn.execute(
        "SELECT name, template_id, session_volume_kg FROM workout_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    return dict(row) if row else None
