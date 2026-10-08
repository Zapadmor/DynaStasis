from __future__ import annotations

from src.core.system_engine import get_or_create_week_id, trigger_cascade_week
from src.database.connection import db_session


def upsert_habit_log(
    date_str: str,
    lecture: bool = False,
    jeune: bool = False,
    status: str | None = None,
    note: str | None = None,
) -> int:
    from datetime import datetime

    jour_label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
    week_id = get_or_create_week_id(date_str)

    with db_session() as conn:
        conn.execute(
            """INSERT INTO habitude_logs
               (date_log, jour_label, semaine_id,
                lecture_10min, jeune_intermittent, status, note_libre)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date_log) DO UPDATE SET
                jour_label         = excluded.jour_label,
                lecture_10min      = excluded.lecture_10min,
                jeune_intermittent = excluded.jeune_intermittent,
                status             = excluded.status,
                note_libre         = excluded.note_libre""",
            (
                date_str,
                jour_label,
                week_id,
                int(lecture),
                int(jeune),
                status,
                note,
            ),
        )

    trigger_cascade_week(week_id)
    return week_id


def get_week_habits(week_id: int) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM habitude_logs WHERE semaine_id = ? ORDER BY date_log",
            (week_id,),
        ).fetchall()
    return [dict(r) for r in rows]
