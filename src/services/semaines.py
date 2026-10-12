from __future__ import annotations

from datetime import datetime, timedelta

from src.core import user_config
from src.database.connection import db_session
from src.repositories import semaines as repo


def debut_et_libelle(date_str: str) -> tuple[str, str]:
    """(lundi ISO, libellé « Audit SNN – jj/mm/aaaa ») de la semaine qui contient la date."""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    monday = date_obj - timedelta(days=date_obj.weekday())
    iso_week = monday.isocalendar()[1]
    return monday.strftime("%Y-%m-%d"), f"Audit S{iso_week:02d} – {monday.strftime('%d/%m/%Y')}"


def delta_hrv(hrv_moy: float | None, hrv_moy_prev: float | None) -> float | None:
    """Écart de HRV moyenne avec la semaine précédente (None si l'une des deux manque)."""
    if hrv_moy is None or hrv_moy_prev is None:
        return None
    return round(hrv_moy - hrv_moy_prev, 1)


def get_or_create_week_id(date_str: str) -> int:
    """
    Retourne l'id de semaine ISO pour une date donnée.
    Crée la ligne dans semaines_audit si elle n'existe pas encore.
    Règle R1 : week_start est la clé naturelle du système.
    """
    week_start, week_label = debut_et_libelle(date_str)

    with db_session() as conn:
        existing = repo.id_par_debut(conn, week_start)
        if existing is not None:
            return existing
        mode_actif = repo.mode_planifie(conn, week_start) or user_config.default_mode()
        return repo.inserer(
            conn, week_start, week_label, mode_actif, repo.est_gelee(conn, week_start)
        )


def trigger_cascade_week(week_id: int) -> None:
    """
    Règle R4 — Cascade : recalcule les rollups focus + habitudes + score
    et met à jour semaines_audit après chaque sync.
    """
    from src.core.focus_manager import get_week_tag_breakdown

    tag_breakdown = get_week_tag_breakdown(week_id)
    focus_engagement_min = tag_breakdown["FORGE_ENGAGEMENT"]
    focus_projets_fond_min = (
        tag_breakdown["FORGE_HARDSKILLS"] + tag_breakdown["FORGE_PRO"] + tag_breakdown["LOGOS"]
    )

    with db_session() as conn:
        repo.maj_cumuls(
            conn,
            week_id,
            deep_focus_min=repo.minutes_deep_focus(conn, week_id),
            habitudes=repo.totaux_habitudes(conn, week_id),
            focus_engagement_min=focus_engagement_min,
            focus_projets_fond_min=focus_projets_fond_min,
        )
        score = repo.score_calcule(conn, week_id)
        if score:
            repo.maj_score(
                conn,
                week_id,
                score["score_semaine"],
                delta_hrv(score["hrv_moy"], score["hrv_moy_prev"]),
            )
