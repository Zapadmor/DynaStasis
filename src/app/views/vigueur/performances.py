"""Onglet « Performances »."""

from __future__ import annotations

import streamlit as st

from src.app.components import (
    PALETTE,
    TRANSPARENT,
)
from src.collectors.workout_db import (
    get_exercise_performance,
    get_exercises,
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB — PERFORMANCES
# ─────────────────────────────────────────────────────────────────────────────


def _tab_performances() -> None:
    import plotly.graph_objects as go

    exercises = get_exercises()
    if not exercises:
        st.markdown("Aucun exercice dans la bibliothèque.")
        return

    ex_names = [e["name"] for e in exercises]
    ex_by_name = {e["name"]: e for e in exercises}

    chosen = st.selectbox("EXERCICE", ex_names, key="perf_exercise_select")
    ex = ex_by_name[chosen]
    perf = get_exercise_performance(ex["id"])

    lbl_weight = "PR LESTE MAX" if ex["load_formula"] == "bw_plus_weight" else "PR POIDS MAX"
    st.markdown(
        f"""
<div style="display:flex;gap:.5rem;margin:0 0 .5rem">
  <div style="flex:1;padding:.6rem .8rem;border-left:2px solid {PALETTE["amber"]}">
    <div style="font-size:.55rem;letter-spacing:.14em;text-transform:uppercase;
                color:{PALETTE["sky_blue"]};font-weight:300;margin-bottom:.25rem">PR REPS</div>
    <div style="font-size:1.7rem;font-weight:300;color:{PALETTE["sky_blue"]};
                line-height:1">{perf["pr_reps"]}</div>
  </div>
  <div style="flex:1;padding:.6rem .8rem;border-left:2px solid {PALETTE["amber"]}">
    <div style="font-size:.55rem;letter-spacing:.14em;text-transform:uppercase;
                color:{PALETTE["sky_blue"]};font-weight:300;margin-bottom:.25rem">{lbl_weight}</div>
    <div style="font-size:1.7rem;font-weight:300;color:{PALETTE["sky_blue"]};
                line-height:1">{perf["pr_weight_kg"]:.1f} kg</div>
  </div>
  <div style="flex:1;padding:.6rem .8rem;border-left:2px solid {PALETTE["amber"]}">
    <div style="font-size:.55rem;letter-spacing:.14em;text-transform:uppercase;
                color:{PALETTE["sky_blue"]};font-weight:300;margin-bottom:.25rem">MEILLEURE SERIE</div>
    <div style="font-size:1.7rem;font-weight:300;color:{PALETTE["sky_blue"]};
                line-height:1">{perf["pr_set_score"]:.0f} kg</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    sessions = perf["sessions"]
    if not sessions:
        st.markdown("Aucune séance enregistrée pour cet exercice.")
        return

    dates = [s["date_entry"] for s in sessions]
    loads = [s["total_load"] for s in sessions]

    fig = go.Figure(
        go.Scatter(
            x=dates,
            y=loads,
            mode="lines+markers",
            line=dict(color=PALETTE["amber"], width=2),
            marker=dict(color=PALETTE["amber"], size=5),
            hovertemplate="%{x}: %{y:.0f} kg<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font_family="Satoshi",
        font_color=PALETTE["sky_blue"],
        font_size=12,
        showlegend=False,
        title=dict(
            text="CHARGE TOTALE PAR SEANCE (kg·reps)",
            font=dict(size=10, weight=300),
            x=0,
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showline=True,
            linecolor=PALETTE["blue_green"],
            linewidth=1,
        ),
        yaxis=dict(showgrid=False, zeroline=False, showline=False),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)
