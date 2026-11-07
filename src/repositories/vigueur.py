"""Requêtes de la page Vigueur : charge d'entraînement, pauses, séances."""

from __future__ import annotations

import sqlite3


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


def pauses(conn: sqlite3.Connection) -> list[dict]:
    """Périodes de gel du système (`system_freezes`), de la plus ancienne à la plus récente."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT date_debut, date_fin, raison FROM system_freezes ORDER BY date_debut ASC"
        )
    ]
