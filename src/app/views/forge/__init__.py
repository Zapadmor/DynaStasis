"""FORGE : objectifs, finances, projets en cours."""

from __future__ import annotations

import streamlit as st

from src.app.views.forge.finance import _tab_finance
from src.app.views.forge.objectifs import _tab_objectifs
from src.app.views.forge.projets import _tab_projets

# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render(current_week: dict | None) -> None:
    st.header("FORGE — Projets & Engagement")

    tab_obj, tab_fin, tab_proj = st.tabs(["Objectifs", "Finance", "Projets en cours"])

    with tab_obj:
        _tab_objectifs()

    with tab_fin:
        _tab_finance()

    with tab_proj:
        _tab_projets()
