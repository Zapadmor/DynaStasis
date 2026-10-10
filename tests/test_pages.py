"""Rendu des pages Streamlit (AppTest) sur une base temporaire."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


def _app(page):
    from src.app.views import dashboard, forge, logos, resonance, systeme, vigueur

    pages = {
        "dashboard": lambda: dashboard.render(None),
        "forge": lambda: forge.render(None),
        "logos": lambda: logos.render(None),
        "vigueur": vigueur.render,
        "resonance": lambda: resonance.render(None),
        "systeme": systeme.render,
    }
    pages[page]()


@pytest.mark.parametrize("page", ["dashboard", "forge", "logos", "vigueur", "resonance", "systeme"])
def test_page_se_rend_sur_base_vide(db, page):
    at = AppTest.from_function(_app, args=(page,), default_timeout=60).run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("page", ["dashboard", "forge", "logos", "vigueur", "resonance", "systeme"])
def test_page_se_rend_sur_base_de_demo(demo_db, page):
    at = AppTest.from_function(_app, args=(page,), default_timeout=60).run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]


def test_historique_journal_avec_semaine_gelee(db, caplog):
    import sqlite3

    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO semaines_audit (week_start, week_label, score_semaine, is_frozen)"
            " VALUES ('2026-03-02', 'S10', 55.0, 0), ('2026-03-09', 'S11', NULL, 1)"
        )

    def app():
        from src.app.views import dashboard

        dashboard._render_history()

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception
    (df,) = [e.value for e in at.dataframe]
    assert sorted(df["Score"].dropna()) == ["55", "freeze"]


def test_systeme_affiche_le_statut_des_sources(db):
    import sqlite3

    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO sync_checkpoints (source, statut, last_success_at, last_error_at,"
            " last_error, last_duration_s) VALUES ('intervals', 'erreur', '2026-10-09 07:00:00',"
            " '2026-10-10 07:00:00', 'Missing secret', 1.5)"
        )

    def app():
        from src.app.views import systeme

        systeme._render_sync_status()

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception
    (df,) = [e.value for e in at.dataframe]
    ligne = df[df["Source"] == "intervals"].iloc[0]
    assert ligne["Statut"] == "Erreur" and "Missing secret" in ligne["Dernière erreur"]
    assert set(df["Source"]) == {"intervals", "strava", "logos", "finance"}
