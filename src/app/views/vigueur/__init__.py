"""VIGUEUR : charge et récupération, séances d'entraînement, performances."""

from __future__ import annotations

import streamlit as st

from src.app.components import CHART_COLORS, PALETTE
from src.app.views.vigueur.charge import (
    _load_data,
    _render_charge_chart,
    _render_hero,
    _render_kpi_strip,
    _render_macro_cycle,
)
from src.app.views.vigueur.performances import _tab_performances
from src.app.views.vigueur.recuperation import _render_recovery_row
from src.app.views.vigueur.workouts import _tab_log_workouts

# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render() -> None:
    st.header("VIGUEUR")

    tab_charge, tab_workouts, tab_perfs = st.tabs(
        ["Charge & Récupération", "Log Workouts", "Performances"]
    )

    with tab_charge:
        df_w, df_d, df_daily = _load_data()

        _render_hero(df_w, df_d)
        _render_kpi_strip(df_w, df_d)
        _render_charge_chart(df_daily)

        st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

        _render_recovery_row(df_w, df_d)

        st.markdown(
            f'<hr style="margin:10px 0 6px;border:none;border-top:1px solid {CHART_COLORS["section_border"]}">',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div style="font-size:.6rem;font-weight:300;color:{PALETTE["blue_green"]};'
            f'letter-spacing:.15em;text-transform:uppercase;margin-bottom:4px">Macro-Cycle 2026</div>',
            unsafe_allow_html=True,
        )
        _render_macro_cycle()

    with tab_workouts:
        _tab_log_workouts()

    with tab_perfs:
        _tab_performances()
