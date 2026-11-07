"""Migrations numérotées : base vide, ancienne base, idempotence."""

from __future__ import annotations

import sqlite3

import pytest

from src.database import connection


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", path)
    return path


def _columns(db_path, table):
    with sqlite3.connect(db_path) as conn:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _version(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def _create_legacy_db(path):
    """Base d'avant les migrations : colonnes manquantes, ancien nom friction_score."""
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE semaines_audit (
                id INTEGER PRIMARY KEY,
                week_start TEXT NOT NULL UNIQUE,
                week_label TEXT NOT NULL,
                friction_score REAL,
                mode_actif TEXT
            );
            CREATE TABLE vigueur_entries (
                id INTEGER PRIMARY KEY,
                date_entry TEXT NOT NULL UNIQUE,
                ctl REAL
            );
            CREATE TABLE npt_personnes (id INTEGER PRIMARY KEY, prenom TEXT NOT NULL);
            CREATE TABLE npt_notes (
                id INTEGER PRIMARY KEY,
                personne_id INTEGER NOT NULL,
                date_note TEXT,
                contenu TEXT NOT NULL
            );
            INSERT INTO semaines_audit (week_start, week_label, friction_score, mode_actif)
                VALUES ('2026-01-05', 'S02', 42.5, 'Cours');
            INSERT INTO vigueur_entries (date_entry, ctl) VALUES ('2026-01-05', 50);
            """
        )


def test_migration_files_are_numbered_without_gap():
    numbers = [n for n, _ in connection._migration_files()]
    assert numbers == list(range(1, len(numbers) + 1))
    assert connection.latest_version() == numbers[-1]


def test_empty_db_reaches_latest_version(tmp_db):
    connection.init_db()
    assert _version(tmp_db) == connection.latest_version()
    assert {"hrv", "sleep_min", "steps"} <= _columns(tmp_db, "vigueur_entries")
    assert {"score_semaine", "is_frozen", "hrv_delta_s1"} <= _columns(tmp_db, "semaines_audit")
    assert "friction_score" not in _columns(tmp_db, "semaines_audit")
    assert "m1_note_recuperation" in _columns(tmp_db, "audit_annuel")
    with sqlite3.connect(tmp_db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.execute("SELECT * FROM v_score_semaine").fetchall()
        conn.execute("SELECT * FROM v_progression_quotidienne").fetchall()
    assert {"system_freezes", "sync_checkpoints", "npt_personnes"} <= tables


def test_legacy_db_reaches_latest_version_and_keeps_data(tmp_db):
    _create_legacy_db(tmp_db)
    assert _version(tmp_db) == 0

    connection.init_db()

    assert _version(tmp_db) == connection.latest_version()
    assert {"hrv", "rhr", "sleep_min", "steps"} <= _columns(tmp_db, "vigueur_entries")
    assert "source" in _columns(tmp_db, "npt_notes")
    assert {"score_semaine", "is_frozen"} <= _columns(tmp_db, "semaines_audit")
    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute("SELECT score_semaine, is_frozen FROM semaines_audit").fetchone()
        assert conn.execute("SELECT ctl FROM vigueur_entries").fetchone() == (50,)
    assert row == (42.5, 0)


def test_migrations_are_idempotent(tmp_db):
    connection.init_db()
    with sqlite3.connect(tmp_db) as conn:
        before = conn.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    # rejeu forcé de toutes les migrations sur une base déjà à jour
    with sqlite3.connect(tmp_db) as conn:
        conn.execute("PRAGMA user_version = 0")
    connection.init_db()
    with sqlite3.connect(tmp_db) as conn:
        after = conn.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    assert _version(tmp_db) == connection.latest_version()
    assert after == before


def test_only_pending_migrations_are_applied(tmp_db):
    connection.init_db()
    with sqlite3.connect(tmp_db) as conn:
        conn.execute("DROP TABLE system_freezes")
    connection.init_db()  # version déjà à jour : 003 n'est pas rejouée
    with sqlite3.connect(tmp_db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "system_freezes" not in tables


def test_failing_migration_keeps_previous_version(tmp_db, tmp_path, monkeypatch):
    mig = tmp_path / "migrations"
    mig.mkdir()
    (mig / "001_ok.sql").write_text("CREATE TABLE a (x INTEGER);\n", encoding="utf-8")
    (mig / "002_ko.sql").write_text("CREATE TABLE b (x INTEGER);\nSELEKT 1;\n", encoding="utf-8")
    monkeypatch.setattr(connection, "MIGRATIONS_DIR", mig)
    with sqlite3.connect(tmp_db) as conn:
        with pytest.raises(sqlite3.OperationalError):
            connection._run_migrations(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_migration_008_sur_base_existante_en_version_7(db):
    """Régression : schema.sql s'exécute avant les migrations, il ne doit pas référencer
    des colonnes qu'une migration n'a pas encore ajoutées."""
    with sqlite3.connect(db) as conn:
        conn.execute("DROP INDEX idx_ws_client_uuid")
        conn.execute("ALTER TABLE workout_sessions DROP COLUMN client_uuid")
        conn.execute("ALTER TABLE workout_session_sets DROP COLUMN rpe")
        conn.execute("PRAGMA user_version = 7")
    connection.init_db()
    assert _version(db) == connection.latest_version() >= 8
    assert "client_uuid" in _columns(db, "workout_sessions")
    assert "rpe" in _columns(db, "workout_session_sets")
    with sqlite3.connect(db) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_ws_client_uuid" in names


def test_migration_009_sur_base_existante_en_version_8(db):
    """Les vues du score référencent workout_min : schema.sql s'exécute avant la migration."""
    with sqlite3.connect(db) as conn:
        conn.execute("DROP VIEW IF EXISTS v_score_semaine")
        for v in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")]:
            conn.execute(f'DROP VIEW IF EXISTS "{v}"')
        conn.execute("ALTER TABLE exercise_library DROP COLUMN unit")
        conn.execute("ALTER TABLE workout_session_sets DROP COLUMN duration_s")
        conn.execute("ALTER TABLE workout_session_sets DROP COLUMN emom_minute")
        conn.execute("ALTER TABLE workout_sessions DROP COLUMN duration_min")
        conn.execute("ALTER TABLE vigueur_entries DROP COLUMN workout_min")
        conn.execute("PRAGMA user_version = 8")
    connection.init_db()
    assert _version(db) == connection.latest_version() >= 9
    assert "unit" in _columns(db, "exercise_library")
    assert {"duration_s", "emom_minute"} <= _columns(db, "workout_session_sets")
    assert "duration_min" in _columns(db, "workout_sessions")
    assert "workout_min" in _columns(db, "vigueur_entries")


def test_migration_010_fixe_la_fraction_des_pompes_sur_base_existante(db):
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE exercise_library DROP COLUMN rep_factor")
        conn.execute("ALTER TABLE exercise_library DROP COLUMN bw_fraction")
        conn.execute(
            "INSERT INTO exercise_library (name, load_formula) VALUES ('Push Up', 'bw_plus_weight')"
        )
        conn.execute(
            "INSERT INTO exercise_library (name, load_formula) VALUES ('Pull Up', 'bw_plus_weight')"
        )
        conn.execute("PRAGMA user_version = 9")
    connection.init_db()
    assert _version(db) == connection.latest_version() >= 10
    with sqlite3.connect(db) as conn:
        rows = dict(conn.execute("SELECT name, bw_fraction FROM exercise_library"))
        factors = {r[0] for r in conn.execute("SELECT rep_factor FROM exercise_library")}
    assert rows == {"Push Up": 0.7, "Pull Up": 1.0}
    assert factors == {1.0}


def test_migration_011_cree_les_tables_du_compteur_sur_base_en_version_10(db):
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE intervals_activities")
        conn.execute("DROP TABLE training_counter")
        conn.execute("PRAGMA user_version = 10")
    connection.init_db()
    assert _version(db) == connection.latest_version() >= 11
    assert {"id", "start_local", "date_entry", "moving_time_s"} <= _columns(
        db, "intervals_activities"
    )
    assert {"baseline_count", "baseline_date", "first_session_id"} <= _columns(
        db, "training_counter"
    )
    with sqlite3.connect(db) as conn:  # aucune valeur personnelle livrée dans le dépôt
        assert conn.execute("SELECT COUNT(*) FROM training_counter").fetchone()[0] == 0


def test_migration_012_ajoute_le_cote_sur_base_en_version_11(db):
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE workout_session_sets DROP COLUMN side")
        conn.execute("PRAGMA user_version = 11")
    connection.init_db()
    assert _version(db) == connection.latest_version() >= 12
    assert "side" in _columns(db, "workout_session_sets")


def test_migration_013_cree_les_index_des_seances_sur_base_en_version_12(db):
    with sqlite3.connect(db) as conn:
        for idx in ("idx_wss_session_ex", "idx_wse_session", "idx_wse_exercise"):
            conn.execute(f"DROP INDEX {idx}")
        conn.execute("PRAGMA user_version = 12")
    connection.init_db()
    assert _version(db) == connection.latest_version() >= 13
    with sqlite3.connect(db) as conn:
        noms = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_wss_session_ex", "idx_wse_session", "idx_wse_exercise"} <= noms
