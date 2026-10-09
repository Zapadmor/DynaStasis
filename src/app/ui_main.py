from __future__ import annotations

import sys
from pathlib import Path

from src.core import user_config
from src.core.tz import today_local

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

today = today_local().isoformat()

with db_session() as conn:
    current_week = conn.execute(
        """SELECT * FROM semaines_audit
           WHERE week_start <= ? AND date(week_start, '+6 days') >= ?""",
        (today, today),
    ).fetchone()

cw = dict(current_week) if current_week else None

pages = [
    st.Page(
        lambda: dashboard.render(cw),
        title="Journal de Bord",
        icon=":material/home:",
        default=True,
        url_path="hub",
    )
]
for pilier, page in (
    (
        "FORGE",
        st.Page(
            lambda: forge.render(cw),
            title="Forge",
            icon=":material/construction:",
            url_path="forge",
        ),
    ),
    (
        "LOGOS",
        st.Page(
            lambda: logos.render(cw), title="Logos", icon=":material/school:", url_path="logos"
        ),
    ),
    (
        "VIGUEUR",
        st.Page(
            vigueur.render, title="Vigueur", icon=":material/directions_run:", url_path="vigueur"
        ),
    ),
    (
        "RESONNANCE",
        st.Page(
            lambda: resonance.render(cw),
            title="Résonnance",
            icon=":material/edit_note:",
            url_path="resonance",
        ),
    ),
    (
        "SYSTEME",
        st.Page(systeme.render, title="Systeme", icon=":material/settings:", url_path="systeme"),
    ),
):
    if user_config.pilier_actif(pilier):
        pages.append(page)

pg = st.navigation(pages, position="sidebar")

components.render_sidebar(cw)

pg.run()
