"""Coefficient de reps proposé à partir des données de l'utilisateur : refuse si peu de données."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "suggest_rep_factor.py"
spec = importlib.util.spec_from_file_location("suggest_rep_factor", SCRIPT)
srf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srf)


def _add(conn, exo, n_sessions, reps, *, weight=0.0, completed=1, set_type="1", start=1):
    conn.execute(
        "INSERT OR IGNORE INTO exercise_library (name, load_formula) VALUES (?, 'bw_plus_weight')",
        (exo,),
    )
    eid = conn.execute("SELECT id FROM exercise_library WHERE name = ?", (exo,)).fetchone()[0]
    for i in range(n_sessions):
        d = f"2099-01-{start + i:02d}"
        sid = conn.execute(
            "INSERT INTO workout_sessions (date_entry, name) VALUES (?, 's')", (d,)
        ).lastrowid
        xid = conn.execute(
            "INSERT INTO workout_session_exercises (session_id, exercise_id, position) VALUES (?, ?, 1)",
            (sid, eid),
        ).lastrowid
        r = reps[i] if isinstance(reps, list) else reps
        conn.execute(
            "INSERT INTO workout_session_sets (session_ex_id, set_index, set_type, weight_kg, reps, completed) "
            "VALUES (?, 0, ?, ?, ?, ?)",
            (xid, set_type, weight, r, completed),
        )


def test_estime_le_rapport_des_medianes(conn):
    _add(conn, "Pull Up", 6, [12, 10, 11, 12, 10, 12])  # médiane 11.5
    _add(conn, "Muscle Up", 6, [4, 5, 4, 6, 5, 5])  # médiane 5
    r = srf.suggest(conn, "Muscle Up", "Pull Up", "2000-01-01", 5)
    assert r["k"] == pytest.approx(11.5 / 5)
    assert r["target"] == (6, 5) and r["reference"] == (6, 11.5)


def test_refuse_avec_trop_peu_de_seances(conn):
    _add(conn, "Pull Up", 6, 10)
    _add(conn, "Muscle Up", 2, 5)
    with pytest.raises(srf.InsufficientData, match=r"2 séance\(s\).*Muscle Up"):
        srf.suggest(conn, "Muscle Up", "Pull Up", "2000-01-01", 5)


def test_ignore_lest_echauffement_et_series_non_validees(conn):
    _add(conn, "Pull Up", 5, 10)
    _add(conn, "Pull Up", 5, 99, weight=10.0, start=10)  # avec lest : exclu
    _add(conn, "Pull Up", 5, 99, set_type="W", start=15)  # échauffement : exclu
    _add(conn, "Pull Up", 5, 99, completed=0, start=20)  # non validée : exclu
    _add(conn, "Muscle Up", 5, 5)
    r = srf.suggest(conn, "Muscle Up", "Pull Up", "2000-01-01", 5)
    assert r["reference"] == (5, 10) and r["k"] == 2.0


def test_cli_refuse_sans_ecrire(db, capsys):
    with sqlite3.connect(db) as c:
        _add(c, "Pull Up", 2, 10)
        _add(c, "Muscle Up", 1, 5)
    before = db.read_bytes()
    assert srf.main(["--target", "Muscle Up", "--db", str(db), "--weeks", "5000"]) == 2
    assert "insuffisantes" in capsys.readouterr().err
    assert db.read_bytes() == before  # lecture seule


def test_cli_affiche_le_coefficient_sans_l_appliquer(db, capsys):
    with sqlite3.connect(db) as c:
        _add(c, "Pull Up", 5, 10)
        _add(c, "Muscle Up", 5, 5)
    assert srf.main(["--target", "Muscle Up", "--db", str(db), "--weeks", "5000"]) == 0
    out = capsys.readouterr().out
    assert (
        "1 Muscle Up = 2.00 Pull Up" in out
        and "UPDATE exercise_library SET rep_factor = 2.00" in out
    )
    with sqlite3.connect(db) as c:
        assert (
            c.execute("SELECT rep_factor FROM exercise_library WHERE name='Muscle Up'").fetchone()[
                0
            ]
            == 1.0
        )
