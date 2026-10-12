from __future__ import annotations

import sys
from pathlib import Path

from src.core.tz import today_local

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from src import pillars
from src.app import components
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
        lambda p=pilier: p.render(cw),
        title=pilier.label,
        icon=pilier.icon,
        default=pilier.key == "HUB",
        url_path=pilier.url_path,
    )
    for pilier in pillars.actifs()
]

pg = st.navigation(pages, position="sidebar")

components.render_sidebar(cw)

pg.run()
