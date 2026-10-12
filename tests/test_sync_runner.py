"""Orchestration des synchronisations : isolation, délai, aucune source, statut en base."""

from __future__ import annotations

import json
import logging
import sys

import pytest

from src.core import sync_runner
from src.core.sync_runner import DELAI, ERREUR, IGNOREE, OK, Source


def _src(key: str, code: str, *, configured: bool = True, timeout: int = 20) -> Source:
    return Source(
        key=key,
        type_sync="vigueur",
        argv=(sys.executable, "-c", code),
        configured=lambda: configured,
        reason="secret absent",
        timeout=timeout,
    )


@pytest.fixture(autouse=True)
def journal(tmp_path, monkeypatch, db):
    """Journal et base dans des dossiers temporaires ; le logger mis en cache est réinitialisé."""
    monkeypatch.setenv("DYNASTASIS_LOG_DIR", str(tmp_path / "logs"))
    log = logging.getLogger("dynastasis.sync")

    def _reset():
        for h in [h for h in log.handlers if getattr(h, "_dynastasis", False)]:
            h.close()
            log.removeHandler(h)

    _reset()
    yield tmp_path / "logs" / "sync.log"
    _reset()


def _statuts(conn):
    return {r["source"]: dict(r) for r in conn.execute("SELECT * FROM sync_checkpoints")}


def test_une_source_qui_leve_ne_bloque_pas_les_autres(conn):
    sources = [
        _src("a", "raise RuntimeError('boum')"),
        _src("b", "print('bien')"),
    ]
    results = sync_runner.run_all(sources)

    assert [r.status for r in results] == [ERREUR, OK]
    assert "boum" in results[0].message
    assert sync_runner.exit_code(results) == 1

    statuts = _statuts(conn)
    assert statuts["a"]["statut"] == ERREUR and "boum" in statuts["a"]["last_error"]
    assert statuts["a"]["last_success_at"] is None
    assert statuts["b"]["statut"] == OK and statuts["b"]["last_success_at"]
    logs = {r["source"]: r["statut"] for r in conn.execute("SELECT * FROM logs_systeme")}
    assert logs == {"a": "erreur", "b": "ok"}


def test_source_lente_interrompue_au_delai(conn):
    sources = [
        _src("lente", "import time; time.sleep(30)", timeout=1),
        _src("rapide", "pass"),
    ]
    results = sync_runner.run_all(sources)

    assert [r.status for r in results] == [DELAI, OK]
    assert results[0].duration_s < 10
    assert sync_runner.exit_code(results) == 1
    assert _statuts(conn)["lente"]["last_error"].startswith("Délai")


def test_aucune_source_configuree(conn, journal):
    results = sync_runner.run_all([_src("a", "pass", configured=False)])

    assert [r.status for r in results] == [IGNOREE]
    assert sync_runner.exit_code(results) == 0
    assert _statuts(conn)["a"]["statut"] == IGNOREE
    assert conn.execute("SELECT COUNT(*) FROM logs_systeme").fetchone()[0] == 0
    events = [json.loads(line)["event"] for line in journal.read_text().splitlines()]
    assert "aucune_source_configuree" in events


def test_la_derniere_erreur_survit_a_une_reussite(conn):
    sync_runner.run_all([_src("a", "raise SystemExit(3)")])
    sync_runner.run_all([_src("a", "pass")])

    ligne = _statuts(conn)["a"]
    assert ligne["statut"] == OK
    assert ligne["last_success_at"] and ligne["last_error_at"] and ligne["last_error"] is not None


def test_journal_json_dans_le_fichier(journal):
    sync_runner.run_all([_src("a", "pass")])
    lignes = [json.loads(line) for line in journal.read_text().splitlines()]
    fin = next(r for r in lignes if r["event"] == "source_fin")
    assert fin["source"] == "a" and fin["status"] == OK and "duration_s" in fin


def test_filtre_only(conn):
    results = sync_runner.run_all([_src("a", "pass"), _src("b", "pass")], only=["b"])
    assert [r.key for r in results] == ["b"]


def test_skip_exclut_des_sources():
    results = sync_runner.run_all([_src("a", "pass"), _src("b", "pass")], skip=["a"])
    assert [r.key for r in results] == ["b"]


def test_variable_d_environnement_exclut_des_sources(monkeypatch):
    monkeypatch.setenv("DYNASTASIS_SYNC_SKIP", "b")
    results = sync_runner.run_all([_src("a", "pass"), _src("b", "pass")])
    assert [r.key for r in results] == ["a"]
