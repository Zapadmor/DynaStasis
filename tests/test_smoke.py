"""Tests de fumée : base initialisable et idempotente, résolution des secrets."""

from __future__ import annotations

import sqlite3
import stat

import pytest

from src import config
from src.core import profile
from src.database import connection


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", path)
    return path


def test_init_db_creates_core_tables(tmp_db):
    connection.init_db()
    with sqlite3.connect(tmp_db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"semaines_audit", "vigueur_entries", "sync_checkpoints"} <= tables


def test_init_db_is_idempotent(tmp_db):
    connection.init_db()
    connection.init_db()  # migrations rejouées sans erreur


def test_db_session_commits_and_rolls_back(tmp_db):
    connection.init_db()
    with connection.db_session() as conn:
        conn.execute("INSERT INTO sync_checkpoints (source, last_date) VALUES ('t', 'x')")
    with pytest.raises(RuntimeError):
        with connection.db_session() as conn:
            conn.execute("INSERT INTO sync_checkpoints (source, last_date) VALUES ('u', 'x')")
            raise RuntimeError
    with connection.db_session() as conn:
        rows = [r[0] for r in conn.execute("SELECT source FROM sync_checkpoints")]
    assert rows == ["t"]


@pytest.fixture
def isolated_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DYNASTASIS_ENV_FILE", str(tmp_path / "secrets.env"))
    monkeypatch.setattr(config, "_env_file_cache", None)
    monkeypatch.setattr(config, "_toml_cache", {})
    monkeypatch.delenv("DEMO_TOKEN", raising=False)


def test_secret_default_when_missing(isolated_secrets):
    assert config.get_secret("demo", "token", "fallback") == "fallback"


def test_secret_from_env_file_then_environ_wins(isolated_secrets, monkeypatch):
    path = config.set_secret("demo", "token", "from-file")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert config.get_secret("demo", "token") == "from-file"

    monkeypatch.setenv("DEMO_TOKEN", "from-env")
    assert config.get_secret("demo", "token") == "from-env"


def test_set_secret_updates_existing_line(isolated_secrets):
    config.set_secret("demo", "token", "one")
    config.set_secret("demo", "token", "two")
    content = config.env_file_path().read_text()
    assert content.count("DEMO_TOKEN=") == 1
    assert config.get_secret("demo", "token") == "two"


def test_init_db_drops_legacy_notion_column(tmp_db):
    connection.init_db()
    with sqlite3.connect(tmp_db) as conn:
        conn.execute("ALTER TABLE semaines_audit ADD COLUMN notion_page_id TEXT")
    connection.init_db()
    with sqlite3.connect(tmp_db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(semaines_audit)")]
    assert "notion_page_id" not in cols


def test_profile_roundtrip_and_defaults(tmp_db, tmp_path):
    connection.init_db()
    assert profile.get_profile("absent", "defaut") == "defaut"
    profile.set_profile("k", {"a": [1, 2], "b": "é"})
    assert profile.get_profile("k") == {"a": [1, 2], "b": "é"}

    out = tmp_path / "p.json"
    assert profile.export_profile(str(out)) == 0
    profile.set_profile("k", "ecrase")
    assert profile.import_profile(str(out)) == 0
    assert profile.get_profile("k") == {"a": [1, 2], "b": "é"}


def test_profile_missing_table_returns_default(tmp_db):
    # base non initialisée : pas d'exception, valeur par défaut
    assert profile.get_profile("x", 42) == 42
