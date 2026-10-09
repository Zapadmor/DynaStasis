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


@pytest.mark.parametrize("page", ["dashboard", "forge", "logos", "vigueur", "resonance", "systeme"])
def test_page_se_rend_sur_base_de_demo(demo_db, page):
    at = AppTest.from_function(_app, args=(page,), default_timeout=60).run()
    assert not at.exception


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
