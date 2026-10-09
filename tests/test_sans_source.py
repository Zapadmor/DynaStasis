"""L'application se rend sans aucune source externe : base vide ou de démo, réseau coupé."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

UI_MAIN = str(Path(__file__).resolve().parents[1] / "src" / "app" / "ui_main.py")


@pytest.fixture(autouse=True)
def reseau_coupe(monkeypatch):
    """Toute tentative de connexion réseau fait échouer le test."""

    def interdit(*args, **kwargs):
        raise AssertionError("appel réseau interdit sans source externe")

    monkeypatch.setattr(socket.socket, "connect", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)
    for var in ("INTERVALS_ICU_API_KEY", "STRAVA_CLIENT_ID", "SAMSUNG_ADB_HOST", "CALENDAR_SRC"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DYNASTASIS_ENV_FILE", "/inexistant/secrets.env")


def _verifie(at):
    assert not at.exception
    assert not at.error, [e.value for e in at.error]


def test_application_complete_sur_base_vide(db):
    _verifie(AppTest.from_file(UI_MAIN, default_timeout=60).run())


def test_application_complete_sur_base_de_demo(demo_db):
    at = AppTest.from_file(UI_MAIN, default_timeout=60).run()
    _verifie(at)
    assert at.metric  # le tableau de bord affiche des indicateurs


def test_aucun_widget_externe_par_defaut(db):
    at = AppTest.from_file(UI_MAIN, default_timeout=60).run()
    assert not any("iframe" in str(m.value) for m in at.markdown)
