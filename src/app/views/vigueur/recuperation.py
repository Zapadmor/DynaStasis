"""Rangée de récupération (HRV, sommeil, distance, pas, écran sur 7 jours)."""

from __future__ import annotations

import streamlit as st

from src.app.components import (
    PALETTE,
    SCREEN_APP_COLORS,
)
from src.app.views.vigueur.commun import _base_layout, _empty_chart, _fmt, _kpi_html, _latest
from src.services import vigueur


def _mini_bars(df, col: str, color: str, height: int = 110) -> None:
    import plotly.graph_objects as go

    if df is None or df.empty or col not in df.columns or df[col].isna().all():
        _empty_chart(height)
        return

    labels = (
        [vigueur.libelle_jour(d) for d in df["date_entry"]]
        if "date_entry" in df.columns
        else list(range(len(df)))
    )
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=df[col],
            marker_color=color,
            marker_line_width=0,
        )
    )
    fig.update_layout(**_base_layout(height))
    fig.update_xaxes(type="category")  # sinon plotly lit « 05/10 » comme une date
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_screen_bars(height: int = 110) -> None:
    """Stacked horizontal bar — top 5 apps, 7 derniers jours. Sans légende."""
    import plotly.graph_objects as go

    rows = vigueur.ecran_top_apps()
    if not rows:
        _empty_chart(height)
        return

    fig = go.Figure()
    for i, row in enumerate(rows):
        name, mins = row["app_name"], row["minutes"]
        fig.add_trace(
            go.Bar(
                name=name,
                x=[mins],
                y=[""],
                orientation="h",
                marker_color=SCREEN_APP_COLORS[i % len(SCREEN_APP_COLORS)],
                marker_line_width=0,
                hovertemplate=f"{name}: %{{x:.0f}} min<extra></extra>",
            )
        )

    layout = _base_layout(height)
    layout.update(
        barmode="stack",
        xaxis=dict(showgrid=False, zeroline=False, showline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showline=False, showticklabels=False),
        margin=dict(l=4, r=4, t=8, b=8),
    )
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_recovery_row(df_w, df_d) -> None:
    import plotly.graph_objects as go

    c_hrv, c_slp, c_dist, c_steps, c_screen = st.columns(5, gap="small")

    # HRV
    with c_hrv:
        hrv = _latest(df_d, "hrv")
        st.markdown(
            _kpi_html("HRV 7j", _fmt(hrv, 0, " ms"), "", PALETTE["blue_green"]),
            unsafe_allow_html=True,
        )
        _mini_bars(df_d, "hrv", PALETTE["blue_green"])

    # Sommeil
    with c_slp:
        slp = _latest(df_d, "sleep_min")
        slp_str = f"{slp / 60:.1f}h" if slp else "—"
        st.markdown(
            _kpi_html("Sommeil 7j", slp_str, "", PALETTE["sky_blue"]),
            unsafe_allow_html=True,
        )
        _mini_bars(df_d, "sleep_min", PALETTE["sky_blue"])

    # Distance hebdo
    with c_dist:
        km = _latest(df_w, "distance_km")
        st.markdown(
            _kpi_html("Distance 7j", _fmt(km, 1, " km"), "", PALETTE["blue_green"]),
            unsafe_allow_html=True,
        )
        if (
            df_w is not None
            and not df_w.empty
            and "distance_km" in df_w.columns
            and df_w["distance_km"].notna().any()
        ):
            last7 = df_w.tail(7)
            fig = go.Figure(
                go.Bar(
                    x=[vigueur.libelle_jour(d) for d in last7["week_start"]],
                    y=last7["distance_km"],
                    marker_color=PALETTE["blue_green"],
                    marker_line_width=0,
                )
            )
            fig.update_layout(**_base_layout(110))
            fig.update_xaxes(type="category")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            _empty_chart(110)

    # Steps 7j
    with c_steps:
        steps = _latest(df_d, "steps")
        steps_str = f"{int(steps):,}".replace(",", " ") if steps else "—"
        st.markdown(
            _kpi_html("Steps 7j", steps_str, "pas · aujourd'hui", PALETTE["amber"]),
            unsafe_allow_html=True,
        )
        _mini_bars(df_d, "steps", PALETTE["amber"])

    # Temps d'écran 7j — stacked bar par app
    with c_screen:
        total_h = vigueur.ecran_total_heures()
        total_str = f"{total_h}h" if total_h else "—"
        st.markdown(
            _kpi_html("Écran 7j", total_str, "top apps", PALETTE["tiger"]),
            unsafe_allow_html=True,
        )
        _render_screen_bars()
