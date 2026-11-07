"""VIGUEUR : courbe de charge et macro-cycle, saisie des séances."""

from __future__ import annotations

import streamlit as st

from src.app.views.vigueur.charge import _load_data, _render_charge_chart, _render_macro_cycle
from src.app.views.vigueur.workouts import _tab_log_workouts

# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render() -> None:
    st.header("VIGUEUR")

    tab_charge, tab_workouts = st.tabs(["Charge & Récupération", "Log Workouts"])

    with tab_charge:
        _render_charge_chart(_load_data())
        _render_macro_cycle()

    with tab_workouts:
        _tab_log_workouts()
