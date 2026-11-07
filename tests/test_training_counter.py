"""Compteur d'entraînements : séances saisies + activités Intervals.icu, point de départ local."""

from __future__ import annotations

import pytest

from bots import vigueur_bot
from src.core import training_counter as tc

BASE, BASE_DATE, FIRST = (
    100,
    "2026-11-05",
    50,
)  # valeurs de test, sans rapport avec des données réelles


def _session(conn, sid, started, *, done=True, link=None):
    conn.execute("INSERT OR IGNORE INTO exercise_library (id, name) VALUES (1, 'X')")
    conn.execute(
        "INSERT INTO workout_sessions (id, date_entry, name, started_at, intervals_activity_id) VALUES (?, ?, 's', ?, ?)",
        (sid, started[:10], started, link),
    )
    conn.execute(
        "INSERT INTO workout_session_exercises (id, session_id, exercise_id, position) VALUES (?, ?, 1, 1)",
        (sid, sid),
    )
    conn.execute(
        "INSERT INTO workout_session_sets (session_ex_id, set_index, set_type, weight_kg, reps, completed) VALUES (?, 0, '1', 0, 5, ?)",
        (sid, 1 if done else 0),
    )


def _activity(conn, aid, start):
    conn.execute(
        "INSERT INTO intervals_activities (id, start_local, date_entry, type) VALUES (?, ?, ?, 'Run')",
        (aid, start, start[:10]),
    )


@pytest.fixture
def configured(conn):
    tc.set_baseline(conn, BASE, BASE_DATE, FIRST)
    return conn


def test_sans_point_de_depart_repli_sur_le_rang_dans_la_base(conn):
    _session(conn, 1, "2026-10-01T10:00:00")
    _session(conn, 2, "2026-10-02T10:00:00", done=False)  # abandonnée : pas de numéro
    _session(conn, 3, "2026-10-03T10:00:00")
    assert tc.next_number(conn) is None
    assert [tc.session_number(conn, i) for i in (1, 3)] == [1, 2]


def test_premiere_seance_apres_le_point_de_depart(configured):
    _session(configured, FIRST, "2026-11-05T17:45:00")
    assert tc.session_number(configured, FIRST) == BASE + 1
    _session(configured, FIRST + 1, "2026-11-06T09:00:00")
    assert tc.session_number(configured, FIRST + 1) == BASE + 2
    assert tc.next_number(configured) == BASE + 3


def test_seances_anterieures_au_point_de_depart_ne_comptent_pas(configured):
    _session(
        configured, FIRST - 5, "2026-10-01T10:00:00"
    )  # historique déjà dans le compteur externe
    _session(configured, FIRST, "2026-11-05T17:45:00")
    assert tc.session_number(configured, FIRST) == BASE + 1


def test_activites_intervals_comptent_apres_la_date_de_depart(configured):
    _activity(configured, "i1", "2026-11-04T08:00:00")  # avant : déjà dans le compteur externe
    _activity(
        configured, "i0", "2026-11-05T19:30:00"
    )  # jour de départ : déjà dans le compteur externe
    _activity(configured, "i2", "2026-11-06T07:00:00")
    _session(configured, FIRST, "2026-11-05T17:45:00")
    _session(configured, FIRST + 1, "2026-11-07T09:00:00")
    assert tc.session_number(configured, FIRST) == BASE + 1
    assert (
        tc.session_number(configured, FIRST + 1) == BASE + 3
    )  # séance 1, activité i2, cette séance
    assert tc.next_number(configured) == BASE + 4


def test_activite_rattachee_a_une_seance_n_est_comptee_qu_une_fois(configured):
    _activity(configured, "i9", "2026-11-06T09:00:00")
    _session(configured, FIRST, "2026-11-06T09:05:00", link="i9")
    assert tc.session_number(configured, FIRST) == BASE + 1
    assert tc.next_number(configured) == BASE + 2


def test_une_activite_plus_ancienne_arrivee_apres_decale_les_numeros(configured):
    """Rang chronologique : comportement attendu, documenté (comme un compteur externe)."""
    _session(configured, FIRST, "2026-11-06T18:00:00")
    assert tc.session_number(configured, FIRST) == BASE + 1
    _activity(configured, "i7", "2026-11-06T07:00:00")  # synchronisée plus tard, mais plus ancienne
    assert tc.session_number(configured, FIRST) == BASE + 2


def test_cli_affiche_et_fixe_le_point_de_depart(db, capsys):
    assert tc.main([]) == 0
    assert "non configuré" in capsys.readouterr().out
    assert tc.main(["set", "500", "--date", "2026-12-01", "--first-session", "7"]) == 0
    out = capsys.readouterr().out
    assert "Point de départ : 500" in out and "Prochain entraînement : #501" in out
    assert tc.main(["set", "600", "--date", "2026-12-02", "--first-session", "8"]) == 0  # remplace
    assert "Point de départ : 600" in capsys.readouterr().out


def test_synchro_enregistre_une_ligne_par_activite_sans_doublon(conn):
    acts = [
        {
            "id": "i1",
            "start_date_local": "2026-11-05T07:00:00",
            "type": "Run",
            "name": "Footing",
            "moving_time": 1800,
            "icu_training_load": 40,
        },
        {
            "id": "i2",
            "start_date_local": "2026-11-05T18:00:00",
            "type": "WeightTraining",
            "moving_time": 900,
        },
        {"start_date_local": "2026-11-05T19:00:00"},  # sans identifiant : ignorée
        {"id": "i3"},  # sans date : ignorée
    ]
    for _ in range(2):  # rejouer la synchro ne duplique rien
        conn.executemany(vigueur_bot._UPSERT_ACTIVITY_ROW, vigueur_bot._activity_rows(acts))
    rows = conn.execute(
        "SELECT id, date_entry, type, moving_time_s FROM intervals_activities ORDER BY id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("i1", "2026-11-05", "Run", 1800.0),
        ("i2", "2026-11-05", "WeightTraining", 900.0),
    ]
