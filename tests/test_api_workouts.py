"""API de saisie mobile : insertion atomique, idempotence, jeton."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

H = {"Authorization": "Bearer secret"}


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setenv("DYNASTASIS_API_TOKEN", "secret")
    return TestClient(app)


def _payload(**kw):
    p = {
        "client_uuid": "uuid-0001-abcd",
        "name": "Force MAX",
        "started_at": "2026-11-05T18:00:00",
        "finished_at": "2026-11-05T19:00:00",
        "bodyweight_kg": 80,
        "exercises": [
            {
                "name": "Pull Up",
                "create": True,
                "sets": [
                    {"set_type": "W", "weight_kg": 0, "reps": 5, "completed": True},
                    {"set_type": "N", "weight_kg": 10, "reps": 8, "rpe": 8, "completed": True},
                    {"set_type": "N", "weight_kg": 10, "reps": 6, "completed": False},
                    {"set_type": "D", "weight_kg": 5, "reps": 6, "completed": True},
                ],
            },
            {
                "name": "Exercice inédit",
                "create": True,
                "sets": [{"set_type": "N", "weight_kg": 20, "reps": 10, "completed": True}],
            },
        ],
    }
    p.update(kw)
    return p


def test_insertion_complete(client, conn):
    conn.execute(
        "INSERT INTO exercise_library (name, load_formula) VALUES ('Pull Up', 'bw_plus_weight')"
    )
    conn.commit()
    r = client.post("/api/workouts", json=_payload(), headers=H)
    assert r.status_code == 200 and r.json()["duplicate"] is False
    sid = r.json()["id"]
    types = [
        x[0]
        for x in conn.execute(
            "SELECT set_type FROM workout_session_sets s JOIN workout_session_exercises e "
            "ON e.id = s.session_ex_id WHERE e.session_id = ? ORDER BY e.position, s.set_index",
            (sid,),
        )
    ]
    assert types == ["W", "1", "2", "D", "1"]
    ws = conn.execute(
        "SELECT date_entry, session_volume_kg FROM workout_sessions WHERE id = ?", (sid,)
    ).fetchone()
    # Pull Up : bw_plus_weight (80+0)*5 + (80+10)*8 + (80+5)*6 ; inédit : 20*10
    assert ws["date_entry"] == "2026-11-05"
    assert ws["session_volume_kg"] == 400 + 720 + 510 + 200
    assert conn.execute("SELECT 1 FROM exercise_library WHERE name = 'Exercice inédit'").fetchone()
    assert conn.execute("SELECT 1 FROM vigueur_entries WHERE date_entry = '2026-11-05'").fetchone()


def test_idempotence(client, conn):
    a = client.post("/api/workouts", json=_payload(), headers=H).json()
    b = client.post("/api/workouts", json=_payload(), headers=H).json()
    assert b == {**a, "duplicate": True}
    assert a["duplicate"] is False
    assert conn.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0] == 1


def test_rollback_si_erreur(client, conn, monkeypatch):
    from src.collectors import workout_db

    orig = workout_db.compute_load

    def boom(*a, **k):
        raise RuntimeError("panne")

    monkeypatch.setattr(workout_db, "compute_load", boom)
    with pytest.raises(RuntimeError):
        TestClient(app, raise_server_exceptions=True).post(
            "/api/workouts", json=_payload(), headers=H
        )
    monkeypatch.setattr(workout_db, "compute_load", orig)
    assert conn.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0] == 0
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM exercise_library WHERE name = 'Exercice inédit'"
        ).fetchone()[0]
        == 0
    )


def test_payload_invalide(client):
    bad = _payload(exercises=[{"name": "X", "sets": [{"set_type": "Z", "reps": 1}]}])
    assert client.post("/api/workouts", json=bad, headers=H).status_code == 422


def test_jeton(client, monkeypatch):
    assert client.post("/api/workouts", json=_payload()).status_code == 401
    assert client.get("/api/history", headers={"Authorization": "Bearer faux"}).status_code == 401
    monkeypatch.delenv("DYNASTASIS_API_TOKEN")
    assert client.get("/api/history", headers=H).status_code == 503
    assert client.get("/api/health").status_code == 200


def test_history_et_precedent(client):
    client.post("/api/workouts", json=_payload(), headers=H)
    hist = client.get("/api/history", headers=H).json()
    assert hist[0]["name"] == "Force MAX" and hist[0]["nb_sets"] == 5
    prev = client.get("/api/exercises", headers=H).json()["previous"]
    assert [s["reps"] for s in prev["Pull Up"]] == [5, 8, 6]


def test_nom_inconnu_refuse_sans_create(client, conn):
    bad = _payload(exercises=[{"name": "Pull Ups", "sets": [{"set_type": "N", "reps": 5}]}])
    conn.execute("INSERT INTO exercise_library (name) VALUES ('Pull Up')")
    conn.commit()
    r = client.post("/api/workouts", json=bad, headers=H)
    assert r.status_code == 422 and "Pull Ups" in r.json()["detail"]
    assert conn.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM exercise_library").fetchone()[0] == 1


def test_nom_insensible_a_la_casse_utilise_la_bibliotheque(client, conn):
    conn.execute("INSERT INTO exercise_library (name) VALUES ('Pull Up')")
    conn.commit()
    ok = _payload(exercises=[{"name": "pull up", "sets": [{"set_type": "N", "reps": 5}]}])
    assert client.post("/api/workouts", json=ok, headers=H).status_code == 200
    assert conn.execute("SELECT COUNT(*) FROM exercise_library").fetchone()[0] == 1


def _template(conn, orphelin=False):
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO exercise_library (id, name, load_formula) VALUES (1, 'Pull Up', 'bw_plus_weight')"
    )
    conn.execute("INSERT INTO workout_templates (id, name) VALUES (1, 'Force MAX')")
    conn.execute(
        "INSERT INTO workout_template_exercises (id, template_id, exercise_id, position) VALUES (1, 1, 1, 1)"
    )
    for i, (t, w, r) in enumerate([("W", 0, 15), ("1", 55, 2), ("2", 50, 3), ("F", 0, 20)]):
        conn.execute(
            "INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps) VALUES (1, ?, ?, ?, ?)",
            (i, t, w, r),
        )
    if orphelin:  # exercice dont la ligne de bibliothèque a disparu
        conn.execute(
            "INSERT INTO workout_template_exercises (id, template_id, exercise_id, position) VALUES (2, 1, 999, 2)"
        )
    conn.commit()


def test_templates_conversion_et_orphelins(client, conn):
    _template(conn, orphelin=True)
    t = client.get("/api/templates", headers=H).json()
    assert len(t) == 1 and t[0]["name"] == "Force MAX" and t[0]["ignored"] == 1
    assert [e["name"] for e in t[0]["exercises"]] == ["Pull Up"]
    assert [s["set_type"] for s in t[0]["exercises"][0]["sets"]] == ["W", "N", "N", "F"]


def test_template_id_enregistre(client, conn):
    _template(conn)
    p = _payload(
        template_id=1,
        exercises=[{"name": "Pull Up", "sets": [{"set_type": "N", "reps": 2, "completed": True}]}],
    )
    sid = client.post("/api/workouts", json=p, headers=H).json()["id"]
    assert (
        conn.execute("SELECT template_id FROM workout_sessions WHERE id = ?", (sid,)).fetchone()[0]
        == 1
    )
    p2 = _payload(client_uuid="uuid-0002-abcd", template_id=424242, exercises=p["exercises"])
    sid2 = client.post("/api/workouts", json=p2, headers=H).json()["id"]
    assert (
        conn.execute("SELECT template_id FROM workout_sessions WHERE id = ?", (sid2,)).fetchone()[0]
        is None
    )


def test_dernier_poids_du_corps(client):
    assert client.get("/api/exercises", headers=H).json()["last_bodyweight_kg"] is None
    client.post("/api/workouts", json=_payload(bodyweight_kg=71.5), headers=H)
    assert client.get("/api/exercises", headers=H).json()["last_bodyweight_kg"] == 71.5


def test_emom_et_formule_a_la_creation(client, conn):
    p = _payload(
        exercises=[
            {
                "name": "Traction lestée",
                "create": True,
                "load_formula": "bw_plus_weight",
                "emom_interval_sec": 60,
                "sets": [{"set_type": "N", "weight_kg": 10, "reps": 5, "completed": True}],
            }
        ],
        bodyweight_kg=80,
    )
    sid = client.post("/api/workouts", json=p, headers=H).json()["id"]
    row = conn.execute(
        "SELECT e.load_formula, x.emom_interval_sec FROM workout_session_exercises x "
        "JOIN exercise_library e ON e.id = x.exercise_id WHERE x.session_id = ?",
        (sid,),
    ).fetchone()
    assert tuple(row) == ("bw_plus_weight", 60)
    vol = conn.execute(
        "SELECT session_volume_kg FROM workout_sessions WHERE id = ?", (sid,)
    ).fetchone()[0]
    assert vol == (80 + 10) * 5


def test_emom_invalide_refuse(client):
    bad = _payload(
        exercises=[{"name": "X", "create": True, "emom_interval_sec": 3, "sets": [{"reps": 1}]}]
    )
    assert client.post("/api/workouts", json=bad, headers=H).status_code == 422


def test_templates_exposent_emom(client, conn):
    _template(conn)
    conn.execute("UPDATE workout_template_exercises SET emom_interval_sec = 60 WHERE id = 1")
    conn.commit()
    t = client.get("/api/templates", headers=H).json()
    assert t[0]["exercises"][0]["emom_interval_sec"] == 60


def _emom_payload(**kw):
    p = {
        "client_uuid": "uuid-emom-0001",
        "name": "EMOM 6",
        "started_at": "2026-11-05T08:00:00",
        "worked_from": "2026-11-05T18:00:10",
        "worked_to": "2026-11-05T18:06:40",
        "bodyweight_kg": 80,
        "exercises": [
            {
                "name": "Pull Up",
                "create": True,
                "load_formula": "bw_plus_weight",
                "emom_interval_sec": 60,
                "sets": [
                    {
                        "weight_kg": 0,
                        "reps": 8,
                        "completed": True,
                        "emom_minute": 1,
                        "duration_s": 38.5,
                    },
                    {
                        "weight_kg": 0,
                        "reps": 8,
                        "completed": True,
                        "emom_minute": 3,
                        "duration_s": 41.2,
                    },
                    {"weight_kg": 0, "reps": 8, "completed": False, "emom_minute": 5},
                ],
            },
            {
                "name": "Planche",
                "create": True,
                "load_formula": "bw_plus_weight",
                "unit": "sec",
                "emom_interval_sec": 60,
                "sets": [
                    {
                        "weight_kg": 0,
                        "reps": 30,
                        "completed": True,
                        "emom_minute": 2,
                        "duration_s": 30,
                    },
                    {
                        "weight_kg": 0,
                        "reps": 30,
                        "completed": True,
                        "emom_minute": 4,
                        "duration_s": 30,
                    },
                    {
                        "weight_kg": 0,
                        "reps": 30,
                        "completed": True,
                        "emom_minute": 6,
                        "duration_s": 30,
                    },
                ],
            },
        ],
    }
    p.update(kw)
    return p


def test_emom_multi_exercices_duree_et_statique(client, conn):
    r = client.post("/api/workouts", json=_emom_payload(), headers=H)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    ws = conn.execute(
        "SELECT date_entry, started_at, finished_at, duration_min, session_volume_kg "
        "FROM workout_sessions WHERE id = ?",
        (sid,),
    ).fetchone()
    # horodatage de la séance réelle (première à dernière action), pas du brouillon
    assert (ws["date_entry"], ws["started_at"], ws["finished_at"]) == (
        "2026-11-05",
        "2026-11-05T18:00:10",
        "2026-11-05T18:06:40",
    )
    assert ws["duration_min"] == 6.5
    # Pull Up (80 kg de corps) : 2 séries x 8 x 80 = 1280 ; la planche (statique) n'ajoute rien
    assert ws["session_volume_kg"] == 1280
    rows = conn.execute(
        "SELECT e.name, e.unit, s.emom_minute, s.duration_s FROM workout_session_sets s "
        "JOIN workout_session_exercises x ON x.id = s.session_ex_id "
        "JOIN exercise_library e ON e.id = x.exercise_id WHERE x.session_id = ? "
        "ORDER BY s.emom_minute",
        (sid,),
    ).fetchall()
    assert [(r[0], r[1], r[2], r[3]) for r in rows][:2] == [
        ("Pull Up", "reps", 1, 38.5),
        ("Planche", "sec", 2, 30.0),
    ]


def test_temps_recopie_dans_le_journal_quotidien(client, conn):
    client.post("/api/workouts", json=_emom_payload(), headers=H)
    row = conn.execute(
        "SELECT workout_min, moving_time_min FROM vigueur_entries WHERE date_entry = '2026-11-05'"
    ).fetchone()
    assert row["workout_min"] == 6.5 and row["moving_time_min"] is None
    # une 2e séance le même jour : somme, recalculée (pas incrémentée)
    p2 = _emom_payload(
        client_uuid="uuid-emom-0002",
        worked_from="2026-11-05T20:00:00",
        worked_to="2026-11-05T20:10:00",
    )
    client.post("/api/workouts", json=p2, headers=H)
    assert (
        conn.execute(
            "SELECT workout_min FROM vigueur_entries WHERE date_entry = '2026-11-05'"
        ).fetchone()[0]
        == 16.5
    )
    # le renvoi d'une séance déjà reçue ne double rien
    client.post("/api/workouts", json=p2, headers=H)
    assert (
        conn.execute(
            "SELECT workout_min FROM vigueur_entries WHERE date_entry = '2026-11-05'"
        ).fetchone()[0]
        == 16.5
    )


def test_synchro_intervals_n_ecrase_pas_workout_min(client, conn):
    from bots import vigueur_bot

    client.post("/api/workouts", json=_emom_payload(), headers=H)
    conn.execute(vigueur_bot._UPSERT_ACTIVITIES, ("2026-11-05", 55.0, 8.0, 52.0))
    conn.commit()
    row = conn.execute(
        "SELECT workout_min, moving_time_min FROM vigueur_entries WHERE date_entry = '2026-11-05'"
    ).fetchone()
    assert (row["workout_min"], row["moving_time_min"]) == (6.5, 52.0)


def test_supprimer_une_seance_recalcule_le_journal(client, conn, db):
    from src.collectors import workout_db

    sid = client.post("/api/workouts", json=_emom_payload(), headers=H).json()["id"]
    workout_db.delete_session(sid)
    assert (
        conn.execute(
            "SELECT workout_min FROM vigueur_entries WHERE date_entry = '2026-11-05'"
        ).fetchone()[0]
        is None
    )


@pytest.mark.parametrize(
    "worked",
    [
        {"worked_from": "2026-11-05T18:00:00"},
        {"worked_from": "2026-11-05T18:00:00", "worked_to": "2026-11-05T17:00:00"},
        {"worked_from": "2026-11-05T01:00:00", "worked_to": "2026-11-05T23:00:00"},
    ],
)
def test_plage_de_travail_invalide_refusee(client, worked):
    p = _emom_payload()
    p.pop("worked_from")
    p.pop("worked_to")
    p.update(worked)
    assert client.post("/api/workouts", json=p, headers=H).status_code == 422


def test_precedent_expose_la_duree(client):
    client.post("/api/workouts", json=_emom_payload(), headers=H)
    prev = client.get("/api/exercises", headers=H).json()
    assert prev["previous"]["Pull Up"][0]["duration_s"] == 38.5
    assert {e["name"]: e["unit"] for e in prev["exercises"]}["Planche"] == "sec"


def test_numero_d_entrainement_et_volume(client, conn):
    # historique : 2 séances avec série validée, 1 abandonnée (aucune série validée)
    conn.execute("INSERT INTO exercise_library (id, name) VALUES (1, 'X')")
    for sid, d, done in [(1, "2026-10-01", 1), (2, "2026-10-02", 0), (3, "2026-10-03", 1)]:
        conn.execute(
            "INSERT INTO workout_sessions (id, date_entry, name) VALUES (?, ?, 's')", (sid, d)
        )
        conn.execute(
            "INSERT INTO workout_session_exercises (id, session_id, exercise_id, position) VALUES (?, ?, 1, 1)",
            (sid, sid),
        )
        conn.execute(
            "INSERT INTO workout_session_sets (session_ex_id, set_index, set_type, weight_kg, reps, completed) VALUES (?, 0, '1', 10, 5, ?)",
            (sid, done),
        )
    conn.commit()
    r1 = client.post("/api/workouts", json=_emom_payload(), headers=H).json()
    assert r1["number"] == 3
    assert (
        r1["volume_kg"] == 2 * 8 * 80
    )  # 2 séries validées de Pull Up (80 kg de corps), planche exclue
    r2 = client.post("/api/workouts", json=_emom_payload(), headers=H).json()  # renvoi
    assert r2["duplicate"] is True and r2["number"] == r1["number"] == 3
    p = _emom_payload(
        client_uuid="uuid-emom-0099",
        worked_from="2026-11-06T09:00:00",
        worked_to="2026-11-06T09:05:00",
    )
    assert client.post("/api/workouts", json=p, headers=H).json()["number"] == 4


def test_volume_renvoye_somme_poids_du_corps_et_lest(client):
    p = _payload(
        bodyweight_kg=80,
        exercises=[
            {
                "name": "Pull Up",
                "create": True,
                "load_formula": "bw_plus_weight",
                "sets": [
                    {"set_type": "N", "weight_kg": 10, "reps": 5, "completed": True},
                    {"set_type": "N", "weight_kg": 10, "reps": 5, "completed": False},
                ],
            }
        ],
    )
    assert client.post("/api/workouts", json=p, headers=H).json()["volume_kg"] == (80 + 10) * 5


def test_precedent_ignore_les_seances_sans_serie_validee(client, conn):
    """Une séance abandonnée plus récente ne doit pas masquer la dernière séance réellement faite."""
    conn.execute("INSERT INTO exercise_library (id, name) VALUES (1, 'Pull Up')")
    for sid, d, done, reps in [(1, "2026-10-01", 1, 9), (2, "2026-10-09", 0, 12)]:
        conn.execute(
            "INSERT INTO workout_sessions (id, date_entry, name) VALUES (?, ?, 's')", (sid, d)
        )
        conn.execute(
            "INSERT INTO workout_session_exercises (id, session_id, exercise_id, position) VALUES (?, ?, 1, 1)",
            (sid, sid),
        )
        conn.execute(
            "INSERT INTO workout_session_sets (session_ex_id, set_index, set_type, weight_kg, reps, completed) VALUES (?, 0, '1', 0, ?, ?)",
            (sid, reps, done),
        )
    conn.commit()
    prev = client.get("/api/exercises", headers=H).json()["previous"]
    assert [s["reps"] for s in prev["Pull Up"]] == [9]


def _vol(client, name, formula, reps, weight=0, bw=80, **lib):
    p = _payload(
        client_uuid=f"uuid-{name}-{reps}-{weight}-xx",
        bodyweight_kg=bw,
        exercises=[
            {
                "name": name,
                "create": True,
                "load_formula": formula,
                "sets": [{"set_type": "N", "weight_kg": weight, "reps": reps, "completed": True}],
            }
        ],
    )
    return client.post("/api/workouts", json=p, headers=H).json()["volume_kg"]


def test_pompes_comptent_une_fraction_du_poids_du_corps(client, conn):
    conn.execute(
        "INSERT INTO exercise_library (name, load_formula, bw_fraction) VALUES ('Push Up', 'bw_plus_weight', 0.7)"
    )
    conn.commit()
    assert _vol(client, "Push Up", "bw_plus_weight", 10) == 80 * 0.7 * 10  # 560
    # le lest s'ajoute en entier : (80 x 0.7 + 10) x 10
    assert _vol(client, "Push Up", "bw_plus_weight", 10, weight=10) == (80 * 0.7 + 10) * 10
    assert (
        conn.execute("SELECT load_kg FROM workout_session_sets ORDER BY id LIMIT 1").fetchone()[0]
        == 56.0
    )


def test_rep_factor_agit_sur_le_volume_pas_sur_la_charge(client, conn):
    conn.execute(
        "INSERT INTO exercise_library (name, load_formula, rep_factor) VALUES ('Muscle Up', 'bw_plus_weight', 2.0)"
    )
    conn.commit()
    assert _vol(client, "Muscle Up", "bw_plus_weight", 5) == 80 * 5 * 2.0  # 800
    assert (
        conn.execute("SELECT load_kg FROM workout_session_sets ORDER BY id LIMIT 1").fetchone()[0]
        == 80.0
    )


def test_sans_coefficient_le_volume_est_inchange(client, conn):
    conn.execute(
        "INSERT INTO exercise_library (name, load_formula) VALUES ('Pull Up', 'bw_plus_weight')"
    )
    conn.commit()
    assert _vol(client, "Pull Up", "bw_plus_weight", 5) == 80 * 5


def test_numero_aligne_sur_le_compteur_externe(client, conn):
    from src.core import training_counter as tc

    tc.set_baseline(conn, 100, "2026-11-05", 1)
    conn.commit()
    r1 = client.post("/api/workouts", json=_emom_payload(), headers=H).json()
    assert r1["number"] == 101
    # activité Intervals.icu après le jour de départ : la séance suivante prend le numéro d'après
    conn.execute(
        "INSERT INTO intervals_activities (id, start_local, date_entry) VALUES ('i1', '2026-11-06T07:00:00', '2026-11-06')"
    )
    conn.commit()
    p2 = _emom_payload(
        client_uuid="uuid-emom-0042",
        worked_from="2026-11-06T09:00:00",
        worked_to="2026-11-06T09:05:00",
    )
    assert client.post("/api/workouts", json=p2, headers=H).json()["number"] == 103
    assert (
        client.post("/api/workouts", json=_emom_payload(), headers=H).json()["number"] == 101
    )  # renvoi : même numéro


def _grips_payload(**kw):
    p = _payload(
        client_uuid="uuid-grips-0001",
        bodyweight_kg=67,
        exercises=[
            {
                "name": "Pronation 90° 3 s",
                "create": True,
                "load_formula": "weight",
                "sets": [
                    {"set_type": "N", "weight_kg": 24, "reps": 1, "completed": True, "side": "D"},
                    {"set_type": "N", "weight_kg": 24, "reps": 1, "completed": True, "side": "G"},
                ],
            },
            {
                "name": "One-arm hold 90°",
                "create": True,
                "unit": "sec",
                "sets": [
                    {"set_type": "N", "weight_kg": 0, "reps": 11.4, "completed": True, "side": "D"},
                    {
                        "set_type": "N",
                        "weight_kg": 0,
                        "reps": 12.62,
                        "completed": True,
                        "side": "G",
                    },
                ],
            },
        ],
    )
    p.update(kw)
    return p


def test_cote_et_secondes_decimales_sont_conserves(client, conn):
    sid = client.post("/api/workouts", json=_grips_payload(), headers=H).json()["id"]
    rows = conn.execute(
        "SELECT e.name, s.side, s.reps FROM workout_session_sets s "
        "JOIN workout_session_exercises x ON x.id = s.session_ex_id "
        "JOIN exercise_library e ON e.id = x.exercise_id WHERE x.session_id = ? "
        "ORDER BY x.position, s.set_index",
        (sid,),
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("Pronation 90° 3 s", "D", 1),
        ("Pronation 90° 3 s", "G", 1),
        ("One-arm hold 90°", "D", 11.4),
        ("One-arm hold 90°", "G", 12.62),
    ]


def test_repetitions_arrondies_a_l_entier_sauf_statique(client, conn):
    p = _payload(
        exercises=[{"name": "Dips", "create": True, "sets": [{"reps": 7.6, "completed": True}]}]
    )
    sid = client.post("/api/workouts", json=p, headers=H).json()["id"]
    assert (
        conn.execute(
            "SELECT s.reps FROM workout_session_sets s JOIN workout_session_exercises x ON x.id = s.session_ex_id "
            "WHERE x.session_id = ?",
            (sid,),
        ).fetchone()[0]
        == 8
    )


def test_cote_invalide_refuse(client):
    p = _grips_payload()
    p["exercises"][0]["sets"][0]["side"] = "X"
    assert client.post("/api/workouts", json=p, headers=H).status_code == 422


def test_maintiens_isometriques_hors_volume_avec_rep_factor_zero(client, conn):
    conn.execute(
        "INSERT INTO exercise_library (name, load_formula, rep_factor) VALUES ('Pronation 90° 3 s', 'weight', 0)"
    )
    conn.commit()
    p = _grips_payload()
    p["exercises"][0].pop("create")
    r = client.post("/api/workouts", json=p, headers=H).json()
    assert r["volume_kg"] == 0.0  # 24 kg x 2 maintiens exclus ; le statique n'a jamais de volume


def test_precedent_renvoie_le_cote(client):
    client.post("/api/workouts", json=_grips_payload(), headers=H)
    prev = client.get("/api/exercises", headers=H).json()["previous"]
    assert [s["side"] for s in prev["Pronation 90° 3 s"]] == ["D", "G"]


def test_precedent_reste_rapide_sur_un_gros_historique(client, conn):
    """Régression : la requête « Préc. » (sous-requête corrélée) prenait 38 s sur ~5 800 séries."""
    import time

    conn.execute("INSERT INTO exercise_library (id, name) VALUES (1, 'A'), (2, 'B'), (3, 'C')")
    conn.executemany(
        "INSERT INTO workout_sessions (id, date_entry, name) VALUES (?, ?, 's')",
        [(i, f"2026-{1 + i % 12:02d}-{1 + i % 27:02d}") for i in range(1, 301)],
    )
    exos = [(i * 10 + k, i, k, k) for i in range(1, 301) for k in (1, 2, 3)]
    conn.executemany(
        "INSERT INTO workout_session_exercises (id, session_id, exercise_id, position) VALUES (?, ?, ?, ?)",
        exos,
    )
    conn.executemany(
        "INSERT INTO workout_session_sets (session_ex_id, set_index, set_type, weight_kg, reps, completed) "
        "VALUES (?, ?, '1', 10, 5, ?)",
        [(se, n, 1 if n < 5 else 0) for se, *_ in exos for n in range(7)],
    )
    conn.commit()
    t = time.perf_counter()
    r = client.get("/api/exercises", headers=H)
    assert r.status_code == 200 and set(r.json()["previous"]) == {"A", "B", "C"}
    assert time.perf_counter() - t < 5, "la requête « Préc. » est redevenue lente"
