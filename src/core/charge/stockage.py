"""Écriture/lecture de la table `charge_locale` (migration 014). Aucun appelant par défaut."""

from __future__ import annotations

import sqlite3

from src.core.charge.endurance import VERSION_ALGO, ChargeLocale


def enregistrer_charge_locale(
    conn: sqlite3.Connection, activity_id: str, date_entry: str, charge: ChargeLocale
) -> None:
    """Insère ou remplace la charge locale d'une activité. L'appelant gère le commit."""
    conn.execute(
        "INSERT OR REPLACE INTO charge_locale"
        " (activity_id, date_entry, charge, methode, confiance, estime, version_algo)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            activity_id,
            date_entry,
            charge.valeur,
            charge.methode,
            charge.confiance,
            int(charge.estime),
            VERSION_ALGO,
        ),
    )


def charge_locale_par_jour(conn: sqlite3.Connection) -> dict[str, float]:
    """Somme de la charge locale par jour (dates ISO)."""
    rows = conn.execute("SELECT date_entry, SUM(charge) FROM charge_locale GROUP BY date_entry")
    return {date: float(total) for date, total in rows}
