from __future__ import annotations

import sys
from pathlib import Path

from src.core.tz import today_paris

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from src.app import components
from src.app.views import dashboard, forge, logos, resonance, systeme, vigueur
from src.database.connection import db_session, init_db

st.set_page_config(
    page_title="DynaStasie",
    page_icon=":material/hub:",
    layout="wide",
    initial_sidebar_state="expanded",
)

components.inject_theme()
init_db()

today = today_paris().isoformat()

with db_session() as conn:
    current_week = conn.execute(
        """SELECT * FROM semaines_audit
           WHERE week_start <= ? AND date(week_start, '+6 days') >= ?""",
        (today, today),
    ).fetchone()

cw = dict(current_week) if current_week else None

pg = st.navigation(
    [
        st.Page(
            lambda: dashboard.render(cw),
            title="Journal de Bord",
            icon=":material/home:",
            default=True,
            url_path="hub",
        ),
        st.Page(
            lambda: forge.render(cw),
            title="Forge",
            icon=":material/construction:",
            url_path="forge",
        ),
        st.Page(
            lambda: logos.render(cw), title="Logos", icon=":material/school:", url_path="logos"
        ),
        st.Page(
            vigueur.render, title="Vigueur", icon=":material/directions_run:", url_path="vigueur"
        ),
        st.Page(
            lambda: resonance.render(cw),
            title="Résonnance",
            icon=":material/edit_note:",
            url_path="resonance",
        ),
        st.Page(systeme.render, title="Systeme", icon=":material/settings:", url_path="systeme"),
    ],
    position="sidebar",
)

components.render_sidebar(cw)

pg.run()
