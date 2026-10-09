"""Mode démo : base fictive, idempotence, garde-fous sur les bases existantes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.core import demo
from src.database import connection


def _count(path, table):
    with sqlite3.connect(path) as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_seed_remplit_les_tables_principales(demo_db):
    for table in (
        "semaines_audit",
        "habitude_logs",
        "focus_sessions",
        "vigueur_entries",
        "screen_sessions",
        "apps_distrayantes",
        "comptes",
        "transactions",
        "objectifs",
        "projets",
        "projet_phases",
        "profil_contenu",
        "workout_sessions",
    ):
        assert _count(demo_db, table) > 0, table
    with sqlite3.connect(demo_db) as c:
        scores = [r[0] for r in c.execute("SELECT score_semaine FROM semaines_audit")]
    assert all(s is not None for s in scores)


def test_seed_est_idempotent_et_deterministe(tmp_path):
    cible = tmp_path / "demo.db"
    demo.seed_demo(cible)
    with sqlite3.connect(cible) as c:
        avant = c.execute("SELECT COUNT(*), SUM(duree_min) FROM focus_sessions").fetchone()
    demo.seed_demo(cible)
    with sqlite3.connect(cible) as c:
        apres = c.execute("SELECT COUNT(*), SUM(duree_min) FROM focus_sessions").fetchone()
    assert avant == apres
    assert _count(cible, "semaines_audit") == demo.NB_WEEKS


def test_seed_restaure_la_base_courante(tmp_path):
    avant = connection.DB_PATH
    demo.seed_demo(tmp_path / "demo.db")
    assert connection.DB_PATH == avant


def test_seed_refuse_la_base_reelle():
    reelle = Path(connection.DEFAULT_DB_PATH)
    with pytest.raises(demo.DemoSeedError, match="base réelle"):
        demo.seed_demo(reelle)


def test_seed_refuse_une_base_non_demo_avec_donnees(db):
    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO semaines_audit (week_start, week_label) VALUES ('2026-03-02', 'S10')"
        )
    with pytest.raises(demo.DemoSeedError, match="refus de les écraser"):
        demo.seed_demo(db)
    assert _count(db, "semaines_audit") == 1


def test_main_seed_demo(tmp_path, monkeypatch, capsys):
    import main

    cible = tmp_path / "cli.db"
    monkeypatch.setattr("sys.argv", ["main.py", "seed-demo", "--db", str(cible)])
    assert main.main() == 0
    assert cible.exists()
    assert "Base créée" in capsys.readouterr().out
