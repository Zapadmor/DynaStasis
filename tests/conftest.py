"""Fixtures partagées : base SQLite temporaire initialisée avec le vrai schéma."""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from src.database import connection


@pytest.fixture(scope="session")
def _db_modele(tmp_path_factory):
    """Base migrée une seule fois, copiée pour chaque test."""
    path = tmp_path_factory.mktemp("modele") / "modele.db"
    mp = pytest.MonkeyPatch()
    mp.setattr(connection, "DB_PATH", path)
    try:
        connection.init_db()
    finally:
        mp.undo()
    with sqlite3.connect(path) as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path


@pytest.fixture
def db(tmp_path, monkeypatch, _db_modele):
    """Chemin d'une base temporaire, migrée jusqu'à la dernière version."""
    path = tmp_path / "test.db"
    shutil.copy(_db_modele, path)
    monkeypatch.setattr(connection, "DB_PATH", path)
    return path


@pytest.fixture
def conn(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON;")
    yield c
    c.close()
