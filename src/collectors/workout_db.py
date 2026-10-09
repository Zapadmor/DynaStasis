from __future__ import annotations

from datetime import datetime

from src.core.tz import now_local
from src.database.connection import db_session


def get_exercises() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, name, category, load_formula FROM exercise_library ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_templates() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute("SELECT id, name FROM workout_templates ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_template_detail(template_id: int) -> dict:
    with db_session() as conn:
        tmpl = conn.execute(
            "SELECT id, name FROM workout_templates WHERE id = ?", (template_id,)
        ).fetchone()
        if not tmpl:
            return {}

        exercises = conn.execute(
            """
            SELECT te.id AS te_id, te.position, te.emom_interval_sec,
                   e.id AS exercise_id, e.name, e.category, e.load_formula
            FROM workout_template_exercises te
            JOIN exercise_library e ON e.id = te.exercise_id
            WHERE te.template_id = ?
            ORDER BY te.position
            """,
            (template_id,),
        ).fetchall()

        result: dict = dict(tmpl)
        result["exercises"] = []
        for ex in exercises:
            sets = conn.execute(
                """
                SELECT set_index, set_type, weight_kg, reps
                FROM workout_template_sets
                WHERE tmpl_exercise_id = ?
                ORDER BY set_index
                """,
                (ex["te_id"],),
            ).fetchall()
            result["exercises"].append(
                {
                    "te_id": ex["te_id"],
                    "position": ex["position"],
                    "exercise_id": ex["exercise_id"],
                    "name": ex["name"],
                    "category": ex["category"],
                    "load_formula": ex["load_formula"],
                    "emom_interval_sec": ex["emom_interval_sec"],
                    "sets": [dict(s) for s in sets],
                }
            )
    return result


def compute_load(weight_kg: float, load_formula: str, bodyweight_kg: float) -> float:
    if load_formula == "bw_plus_weight":
        return bodyweight_kg + weight_kg
    return weight_kg


def create_session(
    date_entry: str,
    template_id: int | None,
    name: str,
    bodyweight_kg: float = 0.0,
) -> int:
    started_at = now_local().isoformat(timespec="seconds")
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO workout_sessions
                (date_entry, template_id, name, started_at, bodyweight_kg)
            VALUES (?, ?, ?, ?, ?)
            """,
            (date_entry, template_id, name, started_at, bodyweight_kg or None),
        )
        session_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO vigueur_entries (date_entry, source, fetched_at)
            VALUES (?, 'manual_workout', datetime('now'))
            ON CONFLICT(date_entry) DO NOTHING
            """,
            (date_entry,),
        )
    return session_id


def save_session_exercises(
    session_id: int,
    exercises: list[dict],
    bodyweight_kg: float = 0.0,
) -> None:
    """
    Replace all exercises+sets for a session.

    exercises: [
        {
            "exercise_id": int,
            "position": int,
            "load_formula": str,
            "sets": [
                {
                    "set_type": str,
                    "weight_kg": float,
                    "reps": int,
                    "completed": bool,
                }
            ]
        }
    ]
    """
    with db_session() as conn:
        conn.execute("DELETE FROM workout_session_exercises WHERE session_id = ?", (session_id,))
        for ex in exercises:
            cur = conn.execute(
                """
                INSERT INTO workout_session_exercises
                    (session_id, exercise_id, position, emom_interval_sec)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, ex["exercise_id"], ex["position"], ex.get("emom_interval_sec")),
            )
            se_id = cur.lastrowid
            formula = ex.get("load_formula", "weight")
            for idx, s in enumerate(ex["sets"]):
                load = compute_load(s["weight_kg"], formula, bodyweight_kg)
                conn.execute(
                    """
                    INSERT INTO workout_session_sets
                        (session_ex_id, set_index, set_type, weight_kg, reps,
                         completed, load_kg)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        se_id,
                        idx,
                        s["set_type"],
                        s["weight_kg"],
                        s["reps"],
                        1 if s.get("completed") else 0,
                        round(load, 2),
                    ),
                )


def finish_session(session_id: int, bodyweight_kg: float = 0.0) -> None:
    """Mark session finished and compute total volume from completed sets."""
    finished_at = now_local().isoformat(timespec="seconds")
    with db_session() as conn:
        # Volume = Σ (load_kg × reps) pour les séries effectuées
        row = conn.execute(
            """
            SELECT COALESCE(SUM(wss.load_kg * wss.reps), 0) AS vol
            FROM workout_session_exercises wse
            JOIN workout_session_sets wss ON wss.session_ex_id = wse.id
            WHERE wse.session_id = ? AND wss.completed = 1
            """,
            (session_id,),
        ).fetchone()
        volume = round(row["vol"], 1) if row else 0.0

        conn.execute(
            """
            UPDATE workout_sessions
            SET finished_at = ?, session_volume_kg = ?, bodyweight_kg = ?
            WHERE id = ?
            """,
            (finished_at, volume, bodyweight_kg or None, session_id),
        )


def update_template_from_session(session_id: int) -> None:
    """Replace template sets with the actual sets from the given session."""
    with db_session() as conn:
        session = conn.execute(
            "SELECT template_id FROM workout_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session or not session["template_id"]:
            return
        template_id = session["template_id"]

        # For each template exercise, find the matching session exercise (by exercise_id+position)
        tmpl_exercises = conn.execute(
            """
            SELECT te.id AS te_id, te.exercise_id, te.position
            FROM workout_template_exercises te
            WHERE te.template_id = ?
            ORDER BY te.position
            """,
            (template_id,),
        ).fetchall()

        session_exercises = conn.execute(
            """
            SELECT wse.exercise_id, wse.position, wse.id AS se_id
            FROM workout_session_exercises wse
            WHERE wse.session_id = ?
            ORDER BY wse.position
            """,
            (session_id,),
        ).fetchall()

        # Build lookup: exercise_id → session exercise id
        se_by_ex = {r["exercise_id"]: r["se_id"] for r in session_exercises}

        for te in tmpl_exercises:
            se_id = se_by_ex.get(te["exercise_id"])
            if se_id is None:
                continue
            # Delete existing template sets and replace
            conn.execute(
                "DELETE FROM workout_template_sets WHERE tmpl_exercise_id = ?",
                (te["te_id"],),
            )
            session_sets = conn.execute(
                """
                SELECT set_index, set_type, weight_kg, reps
                FROM workout_session_sets
                WHERE session_ex_id = ?
                ORDER BY set_index
                """,
                (se_id,),
            ).fetchall()
            for s in session_sets:
                conn.execute(
                    """
                    INSERT INTO workout_template_sets
                        (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (te["te_id"], s["set_index"], s["set_type"], s["weight_kg"], s["reps"]),
                )


def get_exercise_performance(exercise_id: int) -> dict:
    with db_session() as conn:
        pr_reps_row = conn.execute(
            """
            SELECT MAX(wss.reps) AS pr
            FROM workout_session_sets wss
            JOIN workout_session_exercises wse ON wss.session_ex_id = wse.id
            WHERE wse.exercise_id = ? AND wss.completed = 1
            """,
            (exercise_id,),
        ).fetchone()

        pr_weight_row = conn.execute(
            """
            SELECT MAX(wss.weight_kg) AS pr
            FROM workout_session_sets wss
            JOIN workout_session_exercises wse ON wss.session_ex_id = wse.id
            WHERE wse.exercise_id = ? AND wss.completed = 1
            """,
            (exercise_id,),
        ).fetchone()

        pr_set_row = conn.execute(
            """
            SELECT MAX(wss.load_kg * wss.reps) AS pr
            FROM workout_session_sets wss
            JOIN workout_session_exercises wse ON wss.session_ex_id = wse.id
            WHERE wse.exercise_id = ? AND wss.completed = 1
            """,
            (exercise_id,),
        ).fetchone()

        sessions_rows = conn.execute(
            """
            SELECT ws.date_entry, SUM(wss.load_kg * wss.reps) AS total_load
            FROM workout_session_sets wss
            JOIN workout_session_exercises wse ON wss.session_ex_id = wse.id
            JOIN workout_sessions ws ON ws.id = wse.session_id
            WHERE wse.exercise_id = ? AND wss.completed = 1
            GROUP BY ws.id
            ORDER BY ws.date_entry ASC
            """,
            (exercise_id,),
        ).fetchall()

    return {
        "pr_reps": int(pr_reps_row["pr"] or 0),
        "pr_weight_kg": float(pr_weight_row["pr"] or 0.0),
        "pr_set_score": float(pr_set_row["pr"] or 0.0),
        "sessions": [dict(r) for r in sessions_rows],
    }


def delete_session(session_id: int) -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM workout_sessions WHERE id = ?", (session_id,))


def get_sessions(limit: int = 20) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT
                ws.id, ws.date_entry, ws.name,
                ws.started_at, ws.finished_at,
                ws.bodyweight_kg, ws.session_volume_kg,
                ws.intervals_activity_id,
                wt.name AS template_name,
                COUNT(DISTINCT wse.id) AS nb_exercises,
                COUNT(wss.id)          AS nb_sets,
                SUM(CASE WHEN wss.completed = 1 THEN 1 ELSE 0 END) AS nb_completed
            FROM workout_sessions ws
            LEFT JOIN workout_templates wt ON wt.id = ws.template_id
            LEFT JOIN workout_session_exercises wse ON wse.session_id = ws.id
            LEFT JOIN workout_session_sets wss ON wss.session_ex_id = wse.id
            GROUP BY ws.id
            ORDER BY ws.date_entry DESC, ws.started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


_INTERVALS_WORKOUT_TYPES = ("Workout", "WeightTraining")


def sync_intervals_workout_links(
    activities: list[dict],
    max_gap_sec: int = 3 * 3600,
) -> int:
    """
    Link each unlinked workout_session to the Intervals.icu activity of type
    'Workout' or 'WeightTraining' that happened the same day and is closest in
    start time (within ``max_gap_sec``). Each activity is used at most once.
    Returns the number of new links created.
    """
    candidates = [
        a
        for a in activities
        if a.get("type") in _INTERVALS_WORKOUT_TYPES and a.get("id") and a.get("start_date_local")
    ]
    if not candidates:
        return 0

    linked = 0
    with db_session() as conn:
        used = {
            r[0]
            for r in conn.execute(
                "SELECT intervals_activity_id FROM workout_sessions "
                "WHERE intervals_activity_id IS NOT NULL"
            ).fetchall()
        }
        sessions = conn.execute(
            """
            SELECT id, started_at FROM workout_sessions
            WHERE intervals_activity_id IS NULL AND started_at IS NOT NULL
            ORDER BY started_at ASC
            """
        ).fetchall()

        for session in sessions:
            try:
                sdt = datetime.fromisoformat(session["started_at"])
            except ValueError:
                continue

            best_id: str | None = None
            best_diff: float | None = None
            for act in candidates:
                act_id = str(act["id"])
                if act_id in used:
                    continue
                try:
                    adt = datetime.fromisoformat(act["start_date_local"])
                except ValueError:
                    continue
                if adt.date() != sdt.date():
                    continue
                diff = abs((adt - sdt).total_seconds())
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_id = act_id

            if best_id is not None and best_diff is not None and best_diff <= max_gap_sec:
                conn.execute(
                    "UPDATE workout_sessions SET intervals_activity_id = ? WHERE id = ?",
                    (best_id, session["id"]),
                )
                used.add(best_id)
                linked += 1
    return linked


def get_session_detail(session_id: int) -> dict:
    with db_session() as conn:
        session = conn.execute(
            """
            SELECT id, date_entry, name, started_at, finished_at,
                   bodyweight_kg, session_volume_kg
            FROM workout_sessions WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if not session:
            return {}

        exercises = conn.execute(
            """
            SELECT wse.id AS se_id, wse.position, wse.emom_interval_sec,
                   e.id AS exercise_id, e.name, e.load_formula
            FROM workout_session_exercises wse
            JOIN exercise_library e ON e.id = wse.exercise_id
            WHERE wse.session_id = ?
            ORDER BY wse.position
            """,
            (session_id,),
        ).fetchall()

        result = dict(session)
        result["exercises"] = []
        for ex in exercises:
            sets = conn.execute(
                """
                SELECT set_index, set_type, weight_kg, reps, completed, load_kg
                FROM workout_session_sets
                WHERE session_ex_id = ?
                ORDER BY set_index
                """,
                (ex["se_id"],),
            ).fetchall()
            result["exercises"].append(
                {
                    "se_id": ex["se_id"],
                    "position": ex["position"],
                    "exercise_id": ex["exercise_id"],
                    "name": ex["name"],
                    "load_formula": ex["load_formula"],
                    "emom_interval_sec": ex["emom_interval_sec"],
                    "sets": [dict(s) for s in sets],
                }
            )
    return result
