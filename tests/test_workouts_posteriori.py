"""Saisie a posteriori : construction du payload, EMOM, édition, enregistrement identique à la PWA."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from src.api.schemas import WorkoutIn
from src.collectors import workout_db
from src.database.connection import db_session
from src.services import workouts as w

DEBUT = datetime(2026, 11, 6, 18, 30)


def _ligne(reps, kg=0.0, **kw):
    return {
        "type": "N",
        "side": None,
        "kg": kg,
        "reps": reps,
        "rpe": None,
        "minute": None,
        "duree_s": None,
        **kw,
    }


def _exo(name, rows, **info):
    return {
        "kind": "exo",
        "info": {"name": name, "create": False, "load_formula": "weight", "unit": "reps", **info},
        "rows": rows,
    }


def _payload(elements, **kw):
    args = dict(
        name="Séance d'hier",
        debut=DEBUT,
        duree_min=70,
        poids_kg=67.0,
        template_id=None,
        note=None,
        elements=elements,
        client_uuid="uuid-posteriori-1",
    )
    args.update(kw)
    return w.construire_payload(**args)


# ── lignes vides ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("reps", [None, 0, 0.0, "", float("nan")])
def test_ligne_sans_repetitions_est_vide(reps):
    assert w.ligne_vide(_ligne(reps))


def test_ligne_avec_reps_n_est_pas_vide():
    assert not w.ligne_vide(_ligne(5)) and not w.ligne_vide(_ligne(11.4))


def test_series_vides_ignorees_et_exercice_sans_serie_retire():
    p = _payload(
        [_exo("Dips", [_ligne(8, 40), _ligne(None), _ligne(0)]), _exo("Pompes", [_ligne(0)])]
    )
    assert [e["name"] for e in p["exercises"]] == ["Dips"]
    assert len(p["exercises"][0]["sets"]) == 1


# ── payload identique à celui de l'API ───────────────────────────────────────


def test_payload_valide_pour_le_schema_de_l_api():
    p = _payload(
        [
            _exo(
                "Pull Up",
                [_ligne(6, 40), _ligne(6, 40), _ligne(5, 40)],
                load_formula="bw_plus_weight",
            )
        ]
    )
    WorkoutIn(**p)  # même validation que POST /api/workouts
    assert [s["set_type"] for s in p["exercises"][0]["sets"]] == ["N", "N", "N"]
    assert all(s["completed"] for s in p["exercises"][0]["sets"])
    w.numeroter_series(p)  # numérotation faite par l'appelant, après validation
    assert [s["set_type"] for s in p["exercises"][0]["sets"]] == ["1", "2", "3"]


def test_duree_donne_les_bornes_de_travail():
    p = _payload([_exo("X", [_ligne(5)])], duree_min=70)
    assert (p["worked_from"], p["worked_to"]) == ("2026-11-06T18:30:00", "2026-11-06T19:40:00")


def test_sans_duree_pas_de_bornes():
    p = _payload([_exo("X", [_ligne(5)])], duree_min=None)
    assert "worked_from" not in p and "worked_to" not in p


def test_cote_et_secondes_decimales_dans_le_payload():
    p = _payload(
        [_exo("One-arm hold", [_ligne(11.4, side="D"), _ligne(12.62, side="G")], unit="sec")]
    )
    sets = p["exercises"][0]["sets"]
    assert [(s["side"], s["reps"]) for s in sets] == [("D", 11.4), ("G", 12.62)]


# ── EMOM a posteriori ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("n", "minutes", "ok"),
    [(3, 9, True), (3, 10, False), (2, 10, True), (0, 10, False), (3, 2, False)],
)
def test_duree_emom_multiple_du_nombre_d_exercices(n, minutes, ok):
    assert w.duree_emom_valide(n, minutes) is ok


def test_lignes_emom_a_tour_de_role_avec_prerempli():
    infos = [{"name": "Pull Up"}, {"name": "Dips"}]
    prec = {"Pull Up": [{"weight_kg": 0, "reps": 10}, {"weight_kg": 0, "reps": 9}]}
    rows = w.lignes_emom(infos, 6, prec)
    assert [(r["minute"], r["exercice"]) for r in rows] == [
        (1, "Pull Up"),
        (2, "Dips"),
        (3, "Pull Up"),
        (4, "Dips"),
        (5, "Pull Up"),
        (6, "Dips"),
    ]
    assert [r["reps"] for r in rows if r["exercice"] == "Pull Up"] == [
        10,
        9,
        9,
    ]  # dernière série reprise
    assert [r["reps"] for r in rows if r["exercice"] == "Dips"] == [0.0, 0.0, 0.0]


def test_bloc_emom_dans_le_payload_groupe_par_exercice_avec_minute_et_temps():
    infos = [{"name": "Pull Up", "create": False}, {"name": "Dips", "create": False}]
    rows = w.lignes_emom(infos, 4, {})
    for r in rows:
        r["reps"] = 8
    rows[0]["duree_s"] = 38.5
    p = _payload([{"kind": "emom", "infos": infos, "rows": rows}])
    assert [
        (e["name"], e["emom_interval_sec"], [s["emom_minute"] for s in e["sets"]])
        for e in p["exercises"]
    ] == [("Pull Up", 60, [1, 3]), ("Dips", 60, [2, 4])]
    assert p["exercises"][0]["sets"][0]["duration_s"] == 38.5


# ── enregistrement et édition (base) ─────────────────────────────────────────


def _enregistrer(payload):
    w.numeroter_series(payload)
    with db_session() as conn:
        sid, dup = workout_db.import_session(conn, payload)
    return sid, dup


def test_enregistrement_ecrit_volume_duree_et_journal(db):
    elements = [
        _exo(
            "Pull Up",
            [_ligne(6, 40), _ligne(6, 40), _ligne(5, 40)],
            load_formula="bw_plus_weight",
            create=True,
        )
    ]
    sid, _ = _enregistrer(_payload(elements))
    with sqlite3.connect(db) as c:
        vol, dur, d = c.execute(
            "SELECT session_volume_kg, duration_min, date_entry FROM workout_sessions WHERE id=?",
            (sid,),
        ).fetchone()
        wm = c.execute(
            "SELECT workout_min FROM vigueur_entries WHERE date_entry=?", (d,)
        ).fetchone()[0]
    assert vol == (67 + 40) * 17 and dur == 70 and wm == 70 and d == "2026-11-06"


def test_edition_conserve_l_identifiant_et_recalcule(db):
    elements = [_exo("Dips", [_ligne(8, 40)], load_formula="bw_plus_weight", create=True)]
    sid, _ = _enregistrer(_payload(elements))
    with db_session() as conn:
        conn.execute(
            "UPDATE workout_sessions SET intervals_activity_id = 'i42' WHERE id = ?", (sid,)
        )
    edite = _payload(
        [_exo("Dips", [_ligne(8, 40), _ligne(8, 40)], load_formula="bw_plus_weight")],
        debut=datetime(2026, 11, 7, 9, 0),
        duree_min=30,
        client_uuid="uuid-posteriori-2",
    )
    w.numeroter_series(edite)
    with db_session() as conn:
        workout_db.replace_session(conn, sid, edite)
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        s = c.execute("SELECT * FROM workout_sessions WHERE id = ?", (sid,)).fetchone()
        n = c.execute("SELECT COUNT(*) FROM workout_session_sets").fetchone()[0]
        old = c.execute(
            "SELECT workout_min FROM vigueur_entries WHERE date_entry='2026-11-06'"
        ).fetchone()[0]
        new = c.execute(
            "SELECT workout_min FROM vigueur_entries WHERE date_entry='2026-11-07'"
        ).fetchone()[0]
    assert s["intervals_activity_id"] == "i42"  # rattachement Intervals conservé
    assert (s["date_entry"], s["duration_min"], s["session_volume_kg"]) == (
        "2026-11-07",
        30,
        (67 + 40) * 16,
    )
    assert n == 2  # anciennes séries remplacées, pas dupliquées
    assert old is None and new == 30  # minutes de l'ancienne date retirées


def test_edition_d_une_seance_inconnue_refusee(db):
    with pytest.raises(ValueError), db_session() as conn:
        workout_db.replace_session(conn, 999, _payload([_exo("X", [_ligne(5)], create=True)]))


def test_formulaire_depuis_detail_reprend_series_validees_et_emom(db):
    infos = [
        {"name": "Pull Up", "create": True, "load_formula": "bw_plus_weight"},
        {"name": "Dips", "create": True, "load_formula": "bw_plus_weight"},
    ]
    rows = w.lignes_emom(infos, 4, {})
    for r in rows:
        r["reps"] = 8
    elements = [
        _exo("Pronation", [_ligne(1, 24, side="D"), _ligne(1, 24, side="G")], create=True),
        {"kind": "emom", "infos": infos, "rows": rows},
    ]
    sid, _ = _enregistrer(_payload(elements))
    f = w.formulaire_depuis_detail(workout_db.get_session_detail(sid))
    assert f["duree_min"] == 70 and f["poids_kg"] == 67 and f["debut"] == DEBUT
    assert [e["kind"] for e in f["elements"]] == ["exo", "emom"]
    assert [r["side"] for r in f["elements"][0]["rows"]] == ["D", "G"]
    assert [(r["minute"], r["exercice"]) for r in f["elements"][1]["rows"]] == [
        (1, "Pull Up"),
        (2, "Dips"),
        (3, "Pull Up"),
        (4, "Dips"),
    ]
    # aller-retour : le formulaire rechargé redonne le même payload (hors identifiant)
    again = _payload(
        f["elements"],
        name=f["name"],
        debut=f["debut"],
        duree_min=f["duree_min"],
        poids_kg=f["poids_kg"],
    )
    orig = _payload(elements)
    for p in (again, orig):
        p.pop("client_uuid")
        for e in p["exercises"]:
            e.pop("create")
            e.pop("load_formula")
            e.pop("unit")
    assert again["exercises"] == orig["exercises"]


def test_emom_d_un_template_une_serie_par_minute():
    info = {"name": "Pull Up"}
    sets = [
        {"set_type": "1", "weight_kg": 0, "reps": 11},
        {"set_type": "W", "weight_kg": 0, "reps": 5},
    ]
    rows = w.lignes_emom_modele(info, sets)
    assert [(r["minute"], r["exercice"], r["type"], r["reps"]) for r in rows] == [
        (1, "Pull Up", "N", 11),
        (2, "Pull Up", "W", 5),
    ]


def test_numeroter_series_garde_w_f_d():
    p = {"exercises": [{"sets": [{"set_type": t} for t in ("W", "N", "N", "F", "N", "D")]}]}
    w.numeroter_series(p)
    assert [s["set_type"] for s in p["exercises"][0]["sets"]] == ["W", "1", "2", "F", "3", "D"]
