"""Page Vigueur : lecture de la charge, statut de forme, phases du macro-cycle, écran sur 7 jours."""

from __future__ import annotations

import datetime

from src.database.connection import db_session
from src.repositories import vigueur as repo


def statut_phase(debut: str, fin: str, aujourd_hui: datetime.date) -> str:
    """« À VENIR », « EN COURS » ou « PASSÉ » pour une phase datée (bornes incluses)."""
    if aujourd_hui < datetime.date.fromisoformat(debut):
        return "À VENIR"
    if aujourd_hui > datetime.date.fromisoformat(fin):
        return "PASSÉ"
    return "EN COURS"


def statut_forme(tsb: float | None) -> str:
    """Zone de forme selon le TSB (Training Stress Balance)."""
    if tsb is None:
        return "—"
    if tsb < -30:
        return "SURMENAGE"
    if tsb < -10:
        return "OPTIMAL"
    if tsb < 5:
        return "ZONE GRISE"
    if tsb < 20:
        return "FRESH"
    return "TRANSITION"


def libelle_jour(date_iso: str) -> str:
    """« 2026-10-05 » → « 05/10 » (jour/mois), pour les petits graphiques à 7 points."""
    return f"{date_iso[8:10]}/{date_iso[5:7]}"


def donnees_charge() -> tuple[list[dict], list[dict], list[dict]]:
    """(semaines, 7 derniers jours, charge quotidienne), chacun du plus ancien au plus récent.

    Listes vides si la base n'a pas encore les tables (première ouverture)."""
    try:
        with db_session() as conn:
            semaines = repo.hebdo(conn, 26)
            jours = repo.derniers_jours(conn, 7)
            quotidien = repo.charge_quotidienne(conn)
    except Exception:
        return [], [], []
    return (
        sorted(semaines, key=lambda r: r["week_start"]),
        sorted(jours, key=lambda r: r["date_entry"]),
        quotidien,
    )


def ecran_top_apps() -> list[dict]:
    try:
        with db_session() as conn:
            return repo.ecran_top_apps(conn, 5)
    except Exception:
        return []


def ecran_total_heures() -> float | None:
    try:
        with db_session() as conn:
            return repo.ecran_total_heures(conn) or None
    except Exception:
        return None


def resume_seance(session_id: int) -> dict | None:
    with db_session() as conn:
        return repo.resume_seance(conn, session_id)
