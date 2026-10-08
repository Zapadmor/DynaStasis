from __future__ import annotations

from datetime import datetime, timedelta

from src.database.connection import db_session


def get_or_create_week_id(date_str: str) -> int:
    """
    Retourne l'id de semaine ISO pour une date donnée.
    Crée la ligne dans semaines_audit si elle n'existe pas encore.
    Règle R1 : week_start est la clé naturelle du système.
    """
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    monday = date_obj - timedelta(days=date_obj.weekday())
    week_start = monday.strftime("%Y-%m-%d")
    iso_week = monday.isocalendar()[1]
    week_label = f"Audit S{iso_week:02d} – {monday.strftime('%d/%m/%Y')}"

    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM semaines_audit WHERE week_start = ?", (week_start,)
        ).fetchone()
        if row:
            return row["id"]

        mode_row = conn.execute(
            "SELECT lieu FROM sequences_mode WHERE ? BETWEEN date_debut AND date_fin",
            (week_start,),
        ).fetchone()
        mode_actif = mode_row["lieu"] if mode_row else "ecole"

        freeze_row = conn.execute(
            "SELECT 1 FROM system_freezes"
            " WHERE ? <= date_fin AND date(?, '+6 days') >= date_debut LIMIT 1",
            (week_start, week_start),
        ).fetchone()
        is_frozen = 1 if freeze_row else 0

        cur = conn.execute(
            "INSERT INTO semaines_audit (week_start, week_label, mode_actif, is_frozen)"
            " VALUES (?, ?, ?, ?)",
            (week_start, week_label, mode_actif, is_frozen),
        )
        return cur.lastrowid


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
        focus = conn.execute(
            "SELECT minutes_totales FROM v_deep_focus_hebdo WHERE semaine_id = ?",
            (week_id,),
        ).fetchone()
        df_min = focus["minutes_totales"] if focus else 0.0

        habits = conn.execute(
            """SELECT
                COALESCE(SUM(bonne_recup_8h9h), 0)    AS recup,
                COALESCE(SUM(lecture_10min), 0)        AS lecture,
                COALESCE(SUM(sport_marche_45min), 0)   AS sport,
                COALESCE(SUM(jeune_intermittent), 0)   AS jeune
               FROM habitude_logs WHERE semaine_id = ?""",
            (week_id,),
        ).fetchone()

        conn.execute(
            """UPDATE semaines_audit SET
                deep_focus_min          = ?,
                nuits_bonne_recup       = ?,
                sessions_lecture        = ?,
                sessions_sport          = ?,
                sessions_jeune          = ?,
                focus_engagement_min     = ?,
                focus_projets_fond_min  = ?,
                updated_at              = datetime('now')
               WHERE id = ?""",
            (
                df_min,
                habits["recup"],
                habits["lecture"],
                habits["sport"],
                habits["jeune"],
                focus_engagement_min,
                focus_projets_fond_min,
                week_id,
            ),
        )

        score_row = conn.execute(
            "SELECT score_semaine, hrv_moy, hrv_moy_prev FROM v_score_semaine WHERE id = ?",
            (week_id,),
        ).fetchone()
        if score_row:
            hrv_delta: float | None = None
            if score_row["hrv_moy"] is not None and score_row["hrv_moy_prev"] is not None:
                hrv_delta = round(score_row["hrv_moy"] - score_row["hrv_moy_prev"], 1)
            conn.execute(
                "UPDATE semaines_audit SET score_semaine = ?, hrv_delta_s1 = ? WHERE id = ?",
                (score_row["score_semaine"], hrv_delta, week_id),
            )
