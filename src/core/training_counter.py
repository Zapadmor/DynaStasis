"""Compteur d'entraînements : « Entraînement #X », aligné sur un compteur externe (Strava).

Le point de départ (valeur du compteur externe, date, première séance comptée) est saisi localement avec
`python main.py training-counter set ...` ; il n'est jamais écrit dans le dépôt.

Un entraînement compte pour 1 : séance saisie (au moins une série validée, identifiant >= `first_session_id`)
ou activité Intervals.icu (date strictement après `baseline_date` : les activités du jour du départ sont
déjà dans le compteur externe). Une activité rattachée à une séance
(`workout_sessions.intervals_activity_id`) n'est comptée qu'une fois, via la séance. Le numéro est le rang
chronologique : si une activité plus ancienne arrive plus tard, les numéros suivants se décalent.
"""

from __future__ import annotations

import sqlite3
import sys

from src.collectors import workout_db


def get_baseline(conn: sqlite3.Connection) -> sqlite3.Row | tuple | None:
    return conn.execute(
        "SELECT baseline_count, baseline_date, first_session_id FROM training_counter WHERE id = 1"
    ).fetchone()


def set_baseline(
    conn: sqlite3.Connection, count: int, baseline_date: str, first_session_id: int
) -> None:
    conn.execute(
        """
        INSERT INTO training_counter (id, baseline_count, baseline_date, first_session_id)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET baseline_count = excluded.baseline_count,
            baseline_date = excluded.baseline_date, first_session_id = excluded.first_session_id
        """,
        (count, baseline_date, first_session_id),
    )


_SESSION_KEY = "COALESCE(w.started_at, w.date_entry || 'T00:00:00')"
_HAS_DONE_SET = """EXISTS (SELECT 1 FROM workout_session_exercises x
                          JOIN workout_session_sets s ON s.session_ex_id = x.id
                          WHERE x.session_id = w.id AND s.completed = 1)"""


def _count_until(conn: sqlite3.Connection, base, key: str | None) -> int:
    """Entraînements comptés depuis le point de départ, jusqu'à `key` inclus (None = tous)."""
    until_s = f"AND {_SESSION_KEY} <= ?" if key else ""
    sessions = conn.execute(
        f"SELECT COUNT(*) FROM workout_sessions w WHERE w.id >= ? AND {_HAS_DONE_SET} {until_s}",
        (base[2], key) if key else (base[2],),
    ).fetchone()[0]
    until_a = "AND a.start_local <= ?" if key else ""
    activities = conn.execute(
        f"""SELECT COUNT(*) FROM intervals_activities a
            WHERE a.date_entry > ? {until_a}
              AND a.id NOT IN (SELECT intervals_activity_id FROM workout_sessions
                               WHERE intervals_activity_id IS NOT NULL)""",
        (base[1], key) if key else (base[1],),
    ).fetchone()[0]
    return sessions + activities


def session_number(conn: sqlite3.Connection, session_id: int) -> int:
    """Numéro d'une séance. Sans point de départ configuré : rang dans l'historique de la base."""
    base = get_baseline(conn)
    if base is None:
        return workout_db.workout_number(conn, session_id)
    me = conn.execute(
        f"SELECT {_SESSION_KEY} FROM workout_sessions w WHERE w.id = ?", (session_id,)
    ).fetchone()
    if me is None:
        return 0
    return base[0] + _count_until(conn, base, me[0])


def next_number(conn: sqlite3.Connection) -> int | None:
    """Numéro du prochain entraînement, ou None si le compteur n'est pas configuré."""
    base = get_baseline(conn)
    return None if base is None else base[0] + _count_until(conn, base, None) + 1


def main(argv: list[str]) -> int:
    """`training-counter` : état ; `training-counter set COUNT [--date D] [--first-session ID]`."""
    import argparse  # noqa: PLC0415

    from src.core.tz import today_local  # noqa: PLC0415
    from src.database.connection import db_session  # noqa: PLC0415

    p = argparse.ArgumentParser(prog="main.py training-counter")
    sub = p.add_subparsers(dest="action")
    st = sub.add_parser("set", help="fixer le point de départ du compteur")
    st.add_argument(
        "count", type=int, help="valeur du compteur externe avant le premier entraînement compté"
    )
    st.add_argument(
        "--date",
        default=None,
        help="activités Intervals.icu comptées APRÈS cette date (défaut : aujourd'hui)",
    )
    st.add_argument(
        "--first-session",
        type=int,
        required=True,
        help="première séance saisie comptée (identifiant)",
    )
    args = p.parse_args(argv)

    with db_session() as conn:
        if args.action == "set":
            set_baseline(
                conn, args.count, args.date or today_local().isoformat(), args.first_session
            )
        base = get_baseline(conn)
        if base is None:
            print(
                "Compteur non configuré : `python main.py training-counter set COUNT --first-session ID`."
            )
            return 0
        print(
            f"Point de départ : {base[0]} (activités Intervals.icu après le {base[1]}, séances dès l'id {base[2]})"
        )
        print(f"Prochain entraînement : #{next_number(conn)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
