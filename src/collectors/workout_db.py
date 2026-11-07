from __future__ import annotations

from datetime import datetime

from src.database.connection import db_session


def get_exercises() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, name, category, load_formula, unit FROM exercise_library ORDER BY name"
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
                   e.id AS exercise_id, e.name, e.category, e.load_formula, e.unit
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
                    "unit": ex["unit"],
                    "emom_interval_sec": ex["emom_interval_sec"],
                    "sets": [dict(s) for s in sets],
                }
            )
    return result


def compute_load(
    weight_kg: float, load_formula: str, bodyweight_kg: float, bw_fraction: float = 1.0
) -> float:
    """Charge d'une série : le lest s'ajoute en entier, le poids du corps à hauteur de `bw_fraction`."""
    if load_formula == "bw_plus_weight":
        return bodyweight_kg * bw_fraction + weight_kg
    return weight_kg


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


def delete_session(session_id: int) -> None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT date_entry FROM workout_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        conn.execute("DELETE FROM workout_sessions WHERE id = ?", (session_id,))
        if row:
            recompute_workout_min(conn, row["date_entry"])


def get_sessions(limit: int = 20) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT
                ws.id, ws.date_entry, ws.name,
                ws.started_at, ws.finished_at,
                ws.bodyweight_kg, ws.session_volume_kg, ws.duration_min,
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
            SELECT id, date_entry, name, started_at, finished_at, template_id, note,
                   bodyweight_kg, session_volume_kg, duration_min
            FROM workout_sessions WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if not session:
            return {}

        exercises = conn.execute(
            """
            SELECT wse.id AS se_id, wse.position, wse.emom_interval_sec,
                   e.id AS exercise_id, e.name, e.load_formula, e.unit
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
                SELECT set_index, set_type, weight_kg, reps, completed, load_kg, rpe,
                       duration_s, emom_minute, side
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
                    "unit": ex["unit"],
                    "emom_interval_sec": ex["emom_interval_sec"],
                    "sets": [dict(s) for s in sets],
                }
            )
    return result


class UnknownExerciseError(ValueError):
    """Exercice absent de la bibliothèque et non marqué `create` : probable faute de frappe."""

    def __init__(self, names: list[str]):
        super().__init__(", ".join(names))
        self.names = names


def _verifier_exercices(conn, payload: dict) -> None:
    """Refuse un nom absent de la bibliothèque (insensible à la casse) sauf création explicite."""
    inconnus = [
        ex["name"]
        for ex in payload["exercises"]
        if not ex.get("create")
        and conn.execute(
            "SELECT 1 FROM exercise_library WHERE name = ? COLLATE NOCASE", (ex["name"],)
        ).fetchone()
        is None
    ]
    if inconnus:
        raise UnknownExerciseError(inconnus)


def _entete(conn, payload: dict) -> dict:
    """Champs d'en-tête d'une séance : séance réelle = première à dernière action ; sans elles
    (ancien client), horodatages du brouillon."""
    template_id = payload.get("template_id")
    if (
        template_id is not None
        and not conn.execute(
            "SELECT 1 FROM workout_templates WHERE id = ?", (template_id,)
        ).fetchone()
    ):
        template_id = None
    started_at = payload.get("worked_from") or payload["started_at"]
    duration_min = None
    if payload.get("worked_from") and payload.get("worked_to"):
        delta = datetime.fromisoformat(payload["worked_to"]) - datetime.fromisoformat(
            payload["worked_from"]
        )
        duration_min = round(max(delta.total_seconds(), 0) / 60, 1)
    return {
        "date_entry": started_at[:10],
        "template_id": template_id,
        "name": payload["name"],
        "started_at": started_at,
        "finished_at": payload.get("worked_to") or payload.get("finished_at"),
        "note": payload.get("note") or None,
        "bodyweight_kg": payload.get("bodyweight_kg") or None,
        "duration_min": duration_min,
    }


def _ecrire_exercices(conn, session_id: int, payload: dict) -> float:
    """Écrit exercices et séries d'une séance ; retourne le volume (kg) des séries validées."""
    bodyweight = payload.get("bodyweight_kg") or 0.0
    volume = 0.0
    for position, ex in enumerate(payload["exercises"], start=1):
        lib = conn.execute(
            "SELECT id, load_formula, unit, rep_factor, bw_fraction FROM exercise_library "
            "WHERE name = ? COLLATE NOCASE",
            (ex["name"],),
        ).fetchone()
        if lib is None:
            formula = ex.get("load_formula") or "weight"
            unit = ex.get("unit") or "reps"
            rep_factor = bw_fraction = 1.0
            exercise_id = conn.execute(
                "INSERT INTO exercise_library (name, load_formula, unit) VALUES (?, ?, ?)",
                (ex["name"], formula, unit),
            ).lastrowid
        else:
            exercise_id, formula, unit, rep_factor, bw_fraction = (
                lib[0],
                lib[1],
                lib[2],
                lib[3],
                lib[4],
            )
        se_id = conn.execute(
            """
            INSERT INTO workout_session_exercises
                (session_id, exercise_id, position, emom_interval_sec)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, exercise_id, position, ex.get("emom_interval_sec")),
        ).lastrowid
        for idx, s in enumerate(ex["sets"]):
            load = round(compute_load(s["weight_kg"], formula, bodyweight, bw_fraction), 2)
            completed = 1 if s.get("completed") else 0
            # statique : `reps` = secondes (décimales admises) ; sinon un nombre entier de répétitions
            reps = s["reps"] if unit == "sec" else int(round(s["reps"]))
            if completed and unit != "sec":  # statique : pas de volume
                volume += (
                    load * reps * rep_factor
                )  # rep_factor : conversion des reps (1.0 = aucune)
            conn.execute(
                """
                INSERT INTO workout_session_sets
                    (session_ex_id, set_index, set_type, weight_kg, reps, completed, load_kg, rpe,
                     duration_s, emom_minute, side)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    se_id,
                    idx,
                    s["set_type"],
                    s["weight_kg"],
                    reps,
                    completed,
                    load,
                    s.get("rpe"),
                    s.get("duration_s"),
                    s.get("emom_minute"),
                    s.get("side"),
                ),
            )
    return volume


def _journal(conn, date_entry: str) -> None:
    """Garantit la ligne du jour dans `vigueur_entries` et recalcule les minutes d'entraînement."""
    conn.execute(
        """
        INSERT INTO vigueur_entries (date_entry, source, fetched_at)
        VALUES (?, 'manual_workout', datetime('now'))
        ON CONFLICT(date_entry) DO NOTHING
        """,
        (date_entry,),
    )
    recompute_workout_min(conn, date_entry)


def import_session(conn, payload: dict) -> tuple[int, bool]:
    """Insère une séance complète (saisie mobile ou a posteriori) avec la connexion `conn`, sans commit.

    L'appelant fournit la transaction (`db_session`) : tout est écrit ou rien.
    `payload` : name, client_uuid, started_at, finished_at, worked_from, worked_to, note, bodyweight_kg,
    template_id, exercises[{name, create, sets[{set_type, weight_kg, reps, rpe, side, completed}]}].
    Un nom absent de la bibliothèque (comparaison insensible à la casse) lève
    `UnknownExerciseError`, sauf si l'exercice porte `create: True`.
    Retourne (id de séance, déjà_existante) ; un `client_uuid` connu n'est pas réinséré.
    """
    uuid = payload.get("client_uuid")
    if uuid:
        row = conn.execute(
            "SELECT id FROM workout_sessions WHERE client_uuid = ?", (uuid,)
        ).fetchone()
        if row:
            return row[0], True

    _verifier_exercices(conn, payload)
    e = _entete(conn, payload)
    cur = conn.execute(
        """
        INSERT INTO workout_sessions
            (date_entry, template_id, name, started_at, finished_at, note, bodyweight_kg,
             client_uuid, duration_min)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            e["date_entry"],
            e["template_id"],
            e["name"],
            e["started_at"],
            e["finished_at"],
            e["note"],
            e["bodyweight_kg"],
            uuid,
            e["duration_min"],
        ),
    )
    session_id = cur.lastrowid
    volume = _ecrire_exercices(conn, session_id, payload)
    conn.execute(
        "UPDATE workout_sessions SET session_volume_kg = ? WHERE id = ?",
        (round(volume, 1), session_id),
    )
    _journal(conn, e["date_entry"])
    return session_id, False


def replace_session(conn, session_id: int, payload: dict) -> None:
    """Remplace le contenu d'une séance existante **en gardant son identifiant** (édition a posteriori).

    Garder l'id préserve le rattachement Intervals.icu et le rang dans le compteur d'entraînements."""
    ancienne = conn.execute(
        "SELECT date_entry FROM workout_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if ancienne is None:
        raise ValueError(f"Séance {session_id} introuvable")
    _verifier_exercices(conn, payload)
    e = _entete(conn, payload)
    conn.execute(
        """
        UPDATE workout_sessions
        SET date_entry = ?, template_id = ?, name = ?, started_at = ?, finished_at = ?,
            note = ?, bodyweight_kg = ?, duration_min = ?
        WHERE id = ?
        """,
        (
            e["date_entry"],
            e["template_id"],
            e["name"],
            e["started_at"],
            e["finished_at"],
            e["note"],
            e["bodyweight_kg"],
            e["duration_min"],
            session_id,
        ),
    )
    conn.execute("DELETE FROM workout_session_exercises WHERE session_id = ?", (session_id,))
    volume = _ecrire_exercices(conn, session_id, payload)
    conn.execute(
        "UPDATE workout_sessions SET session_volume_kg = ? WHERE id = ?",
        (round(volume, 1), session_id),
    )
    _journal(conn, e["date_entry"])
    if ancienne["date_entry"] != e["date_entry"]:
        recompute_workout_min(conn, ancienne["date_entry"])


def workout_number(conn, session_id: int) -> int:
    """Rang de la séance dans l'historique (« Entraînement n° X »).

    Compte les séances ayant au moins une série validée, classées par date puis identifiant :
    les séances vides ou abandonnées ne consomment pas de numéro, et le rang d'une séance donnée
    reste stable (un renvoi affiche le même numéro).
    """
    me = conn.execute(
        "SELECT date_entry FROM workout_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if me is None:
        return 0
    return conn.execute(
        """
        SELECT COUNT(*) FROM workout_sessions w
        WHERE EXISTS (
            SELECT 1 FROM workout_session_exercises x
            JOIN workout_session_sets s ON s.session_ex_id = x.id
            WHERE x.session_id = w.id AND s.completed = 1)
          AND (w.date_entry < ? OR (w.date_entry = ? AND w.id <= ?))
        """,
        (me["date_entry"], me["date_entry"], session_id),
    ).fetchone()[0]


def recompute_workout_min(conn, date_entry: str) -> None:
    """Recopie dans `vigueur_entries.workout_min` la somme des durées PWA du jour.

    Recalculée depuis `workout_sessions` (jamais incrémentée) : un renvoi ou une suppression ne
    fait pas dériver le total. La synchro Intervals.icu n'écrit pas cette colonne.
    """
    conn.execute(
        """
        UPDATE vigueur_entries
        SET workout_min = (
            SELECT ROUND(SUM(duration_min), 1) FROM workout_sessions
            WHERE date_entry = ? AND duration_min IS NOT NULL)
        WHERE date_entry = ?
        """,
        (date_entry, date_entry),
    )


def last_sets_by_exercise(conn) -> dict[str, list[dict]]:
    """Séries de la dernière séance validée de chaque exercice (colonne « Précédent »).

    Une séance sans aucune série validée (abandonnée) est ignorée. Une seule passe par fenêtre : une
    sous-requête corrélée par ligne coûtait 38 s sur l'historique réel."""
    rows = conn.execute(
        """
        WITH faites AS (
            SELECT wse.id AS se_id, wse.exercise_id, ws.date_entry, ws.id AS session_id
            FROM workout_session_exercises wse
            JOIN workout_sessions ws ON ws.id = wse.session_id
            WHERE EXISTS (SELECT 1 FROM workout_session_sets q
                          WHERE q.session_ex_id = wse.id AND q.completed = 1)
        ),
        derniere AS (
            SELECT se_id, exercise_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY exercise_id
                       ORDER BY date_entry DESC, session_id DESC, se_id DESC) AS rang
            FROM faites
        )
        SELECT e.name, d.se_id, wss.set_index, wss.set_type, wss.weight_kg, wss.reps,
               wss.duration_s, wss.side
        FROM derniere d
        JOIN exercise_library e ON e.id = d.exercise_id
        JOIN workout_session_sets wss ON wss.session_ex_id = d.se_id
        WHERE d.rang = 1 AND wss.completed = 1
        ORDER BY e.name, wss.set_index
        """
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["name"], []).append(
            {
                "set_type": r["set_type"],
                "weight_kg": r["weight_kg"],
                "reps": r["reps"],
                "duration_s": r["duration_s"],
                "side": r["side"],
            }
        )
    return out


def get_templates_for_pwa(conn) -> list[dict]:
    """Templates avec exercices et séries prévues, au format de la PWA.

    Types de série : 'W', 'F', 'D' conservés, séries de travail ('1', '2'…) → 'N'.
    Un exercice dont la ligne `exercise_library` a disparu est ignoré et compté dans `ignored`.
    """
    out = []
    for t in conn.execute("SELECT id, name FROM workout_templates ORDER BY name"):
        exercises, ignored = [], 0
        for te in conn.execute(
            """
            SELECT te.id, te.position, te.emom_interval_sec, e.name, e.unit
            FROM workout_template_exercises te
            LEFT JOIN exercise_library e ON e.id = te.exercise_id
            WHERE te.template_id = ? ORDER BY te.position
            """,
            (t["id"],),
        ):
            if te["name"] is None:
                ignored += 1
                continue
            sets = [
                {
                    "set_type": s["set_type"] if s["set_type"] in ("W", "F", "D") else "N",
                    "weight_kg": s["weight_kg"],
                    "reps": s["reps"],
                }
                for s in conn.execute(
                    "SELECT set_type, weight_kg, reps FROM workout_template_sets "
                    "WHERE tmpl_exercise_id = ? ORDER BY set_index",
                    (te["id"],),
                )
            ]
            exercises.append(
                {
                    "name": te["name"],
                    "unit": te["unit"],
                    "emom_interval_sec": te["emom_interval_sec"],
                    "sets": sets,
                }
            )
        out.append({"id": t["id"], "name": t["name"], "exercises": exercises, "ignored": ignored})
    return out


def last_bodyweight(conn) -> float | None:
    """Poids du corps de la dernière séance qui en porte un (valeur par défaut de la PWA)."""
    row = conn.execute(
        "SELECT bodyweight_kg FROM workout_sessions WHERE bodyweight_kg IS NOT NULL "
        "ORDER BY date_entry DESC, id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None
