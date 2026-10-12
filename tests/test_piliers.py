"""Registre de piliers : navigation, commandes CLI et sources de synchronisation."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import pillars
from src.core import sync_runner, user_config
from src.pillars.base import Command, Pilier

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    def _set(contenu: str):
        path = tmp_path / "user.toml"
        path.write_text(contenu, encoding="utf-8")
        monkeypatch.setenv("DYNASTASIS_CONFIG", str(path))
        user_config.reload()

    yield _set
    monkeypatch.delenv("DYNASTASIS_CONFIG", raising=False)
    user_config.reload()


def test_ordre_de_navigation_stable():
    assert [p.key for p in pillars.all_piliers()] == [
        "HUB",
        "FORGE",
        "LOGOS",
        "VIGUEUR",
        "RESONNANCE",
        "SYSTEME",
    ]
    assert pillars.keys() == ["FORGE", "LOGOS", "VIGUEUR", "RESONNANCE", "SYSTEME"]
    assert [p.key for p in pillars.actifs()] == [p.key for p in pillars.all_piliers()]


def test_pilier_inactif_absent_de_la_navigation(cfg):
    cfg('[piliers]\nactifs = ["FORGE", "SYSTEME"]\n')
    assert [p.key for p in pillars.actifs()] == ["HUB", "FORGE", "SYSTEME"]


def test_pilier_inactif_sans_sources_de_synchro(cfg):
    cfg('[piliers]\nactifs = ["FORGE", "SYSTEME"]\n')
    assert [s.key for s in sync_runner.default_sources()] == ["finance"]


def test_sources_dans_l_ordre_historique():
    assert [s.key for s in sync_runner.default_sources()] == [
        "intervals",
        "strava",
        "logos",
        "finance",
    ]


def test_pilier_sans_sync_ni_source():
    resonance = next(p for p in pillars.all_piliers() if p.key == "RESONNANCE")
    assert resonance.sync is None
    assert resonance.cli_commands() == ()
    assert resonance.sources() == []


def test_commandes_cli_declarees_par_les_piliers():
    assert set(pillars.commands()) == {"vigueur", "logos", "finance", "strava-auth"}


def test_commande_en_double_refusee(monkeypatch):
    def _noop(argv):
        return 0

    doublon = Pilier(
        "X",
        "X",
        "",
        "x",
        render=lambda cw: None,
        sync=Command("logos", "", _noop),
    )
    existants = pillars.all_piliers()
    monkeypatch.setattr(pillars, "all_piliers", lambda: (*existants, doublon))
    with pytest.raises(ValueError, match="en double"):
        pillars.commands()


def test_configuration_valide_les_codes_via_le_registre(cfg):
    with pytest.raises(user_config.ConfigError):
        cfg('[piliers]\nactifs = ["HUB"]\n')


def test_navigation_filtree_par_la_configuration(demo_db, cfg):
    cfg('[piliers]\nactifs = ["VIGUEUR"]\n')

    def app():
        from src import pillars

        pages = [p.label for p in pillars.actifs()]
        import streamlit as st

        st.write(pages)

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception
    assert at.json[0].value == '["Journal de Bord", "Vigueur"]'


def test_application_complete_navigue_via_le_registre(demo_db, cfg):
    cfg('[piliers]\nactifs = ["FORGE", "SYSTEME"]\n')
    at = AppTest.from_file(str(ROOT / "src" / "app" / "ui_main.py"), default_timeout=60).run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
