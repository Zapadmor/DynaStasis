"""Onglet « Charge & Récupération » : en-tête, KPI, courbe CTL/ATL/TSB, macro-cycle."""

from __future__ import annotations

import datetime

import streamlit as st

from src.app.components import (
    CHART_COLORS,
    GRAY,
    PALETTE,
    TRANSPARENT,
    VIGUEUR_COLORS,
)
from src.app.views.vigueur.commun import (
    _fmt,
    _form_status,
    _kpi_html,
    _latest,
    _macro_cycle,
    _phase_status,
    _vo2max_actuel,
)
from src.core.profile import get_profile
from src.core.tz import today_local
from src.services import vigueur

# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────


def _load_data() -> tuple:
    try:
        import pandas as pd
    except ImportError:
        return None, None, None

    semaines, jours, quotidien = vigueur.donnees_charge()
    return pd.DataFrame(semaines), pd.DataFrame(jours), pd.DataFrame(quotidien)


# ─────────────────────────────────────────────────────────────────────────────
# SECTIONS
# ─────────────────────────────────────────────────────────────────────────────


def _render_hero(df_w, df_d) -> None:
    today = today_local()
    phase = next(
        (p for p in _macro_cycle() if _phase_status(p["Début"], p["Fin"]) == "EN COURS"),
        None,
    )
    tsb = _latest(df_d, "tsb")
    form_label, form_color = _form_status(tsb)

    if phase:
        days_left = (datetime.date.fromisoformat(phase["Fin"]) - today).days
        phase_txt = f"{phase['Phase'].upper()}  ·  {phase['Focus']}  ·  {days_left}J"
    else:
        phase_txt = "AUCUNE PHASE ACTIVE"

    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:2px 0 6px">'
        f'<span style="font-size:.68rem;font-weight:300;color:{PALETTE["blue_green"]};'
        f'letter-spacing:.14em">{phase_txt}</span>'
        f'<span style="font-size:.6rem;font-weight:600;color:{form_color};'
        f'letter-spacing:.1em;border:1px solid {form_color};padding:2px 10px">'
        f"{form_label}</span>"
        f"</div>"
        f'<div style="font-size:.58rem;color:{PALETTE["sky_blue"]};opacity:.5;'
        f'letter-spacing:.1em;margin-bottom:6px">'
        f"{get_profile('vigueur.objectif_course', '')}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_kpi_strip(df_w, df_d) -> None:
    # CTL/ATL/TSB from most recent daily entry (not weekly average)
    ctl = _latest(df_d, "ctl")
    atl = _latest(df_d, "atl")
    tsb = _latest(df_d, "tsb")
    vo2 = _latest(df_w, "vo2max") or _vo2max_actuel()
    tss = _latest(df_w, "tss_total")

    tsb_color = _form_status(tsb)[1]

    items = [
        ("CTL", _fmt(ctl, 0), "Fitness", PALETTE["blue_green"]),
        ("ATL", _fmt(atl, 0), "Fatigue", PALETTE["tiger"]),
        ("Forme", _fmt(tsb, 1), "TSB", tsb_color),
        ("VO2max", _fmt(vo2, 1), "mL/kg/min", PALETTE["amber"]),
        ("TSS", _fmt(tss, 0), "/semaine", PALETTE["sky_blue"]),
    ]
    strip = (
        '<div style="display:flex;justify-content:space-evenly;'
        'align-items:flex-start;flex-wrap:nowrap;gap:0">'
        + "".join(_kpi_html(lbl, v, s, c) for lbl, v, s, c in items)
        + "</div>"
    )
    st.markdown(strip, unsafe_allow_html=True)

    st.markdown(
        f'<hr style="margin:2px 0 8px;border:none;border-top:1px solid {PALETTE["blue_green"]};opacity:.2">',
        unsafe_allow_html=True,
    )


_RANGE_DAYS = {"1S": 7, "1M": 30, "3M": 91, "6M": 182, "1A": 365, "TOUT": 9999}

_TSB_ZONES = [
    # (y0, y1, fill_color, label, label_color)
    (20, 200, CHART_COLORS["tsb_transition_fill"], "TRANSITION", GRAY),
    (5, 20, CHART_COLORS["tsb_fresh_fill"], "FRESH", VIGUEUR_COLORS["fresh"]),
    (-10, 5, CHART_COLORS["tsb_grey_fill"], "GREY ZONE", GRAY),
    (-30, -10, CHART_COLORS["tsb_optimal_fill"], "OPTIMAL", VIGUEUR_COLORS["optimal"]),
    (-200, -30, CHART_COLORS["tsb_highrisk_fill"], "HIGH RISK", PALETTE["tiger"]),
]


def _render_charge_chart(df_daily) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if df_daily is None or df_daily.empty:
        st.caption("Aucune donnée — lancez `python main.py vigueur`.")
        return

    # ── Time range selector (query params pour partage URL) ───────
    keys = list(_RANGE_DAYS.keys())
    try:
        qp_range = st.query_params.get("vigueur_range", "3M")
        default_idx = keys.index(qp_range) if qp_range in keys else 2
    except Exception:
        default_idx = 2

    sel = st.radio(
        "range",
        keys,
        index=default_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="vigueur_range_radio",
    )
    st.query_params["vigueur_range"] = sel

    cutoff = (today_local() - datetime.timedelta(days=_RANGE_DAYS[sel])).isoformat()
    df = df_daily[df_daily["date_entry"] >= cutoff].copy()
    if df.empty:
        df = df_daily.copy()

    # Indicateur de données disponibles
    n_days = len(df)
    data_from = df["date_entry"].min() if not df.empty else "—"
    st.markdown(
        f'<div style="font-size:.58rem;color:{GRAY};letter-spacing:.08em;'
        f'margin:-4px 0 4px">{n_days} jours · {data_from}</div>',
        unsafe_allow_html=True,
    )

    has_tss = "tss" in df.columns and df["tss"].notna().any()

    # ── Dual-panel figure (secondary_y pour les barres TSS) ───────
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.58, 0.42],
        vertical_spacing=0.02,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )

    # Barres TSS sur axe secondaire (droite, hidden labels)
    if has_tss:
        fig.add_trace(
            go.Bar(
                x=df["date_entry"],
                y=df["tss"],
                name="Charge (TSS)",
                marker_color=VIGUEUR_COLORS["tss_bar"],
                marker_line_width=0,
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    # CTL + ATL sur axe primaire (gauche)
    fig.add_trace(
        go.Scatter(
            x=df["date_entry"],
            y=df["ctl"],
            mode="lines",
            name="Fitness (CTL)",
            line=dict(color=VIGUEUR_COLORS["ctl_moy"], width=2),
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["date_entry"],
            y=df["atl"],
            mode="lines",
            name="Fatigue (ATL)",
            line=dict(color=VIGUEUR_COLORS["atl_moy"], width=2),
        ),
        row=1,
        col=1,
        secondary_y=False,
    )

    # Panel 2 — TSB / Form + zones
    for y0, y1, fill, label, lcolor in _TSB_ZONES:
        fig.add_hrect(
            y0=y0,
            y1=y1,
            fillcolor=fill,
            line_width=0,
            annotation_text=label,
            annotation_position="left",
            annotation_font=dict(size=8, color=lcolor),
            row=2,
            col=1,
        )
    fig.add_hline(
        y=0, line_dash="dot", line_color=CHART_COLORS["tsb_zero_line"], line_width=1, row=2, col=1
    )

    # Courbe TSB
    fig.add_trace(
        go.Scatter(
            x=df["date_entry"],
            y=df["tsb"],
            mode="lines",
            name="Form (TSB)",
            line=dict(color=VIGUEUR_COLORS["tsb_moy"], width=1.6),
            fill="tozeroy",
            fillcolor=VIGUEUR_COLORS["tsb_fill"],
        ),
        row=2,
        col=1,
    )

    # Dot sur la valeur la plus récente
    last = df.iloc[-1]
    tsb_last = last.get("tsb") if hasattr(last, "get") else last["tsb"]
    if tsb_last is not None:
        fig.add_trace(
            go.Scatter(
                x=[last["date_entry"]],
                y=[tsb_last],
                mode="markers",
                marker=dict(size=8, color=PALETTE["amber"]),
                showlegend=False,
                hovertemplate=f"Form: {tsb_last:.1f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    # ── Layout ────────────────────────────────────────────────────
    axis_style = dict(
        showgrid=False,
        zeroline=False,
        showline=False,
        tickfont=dict(size=8, color=PALETTE["sky_blue"]),
    )
    xaxis_style = dict(
        showgrid=False,
        zeroline=False,
        showline=True,
        linecolor=PALETTE["blue_green"],
        linewidth=1,
        tickfont=dict(size=8, color=PALETTE["sky_blue"]),
    )

    fig.update_layout(
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font_family="Satoshi",
        font_color=PALETTE["sky_blue"],
        font_size=9,
        height=290,
        margin=dict(l=36, r=10, t=28, b=10),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=9), bgcolor=TRANSPARENT
        ),
        bargap=0.1,
    )
    # Axes CTL/ATL (primary left)
    fig.update_yaxes(secondary_y=False, row=1, col=1, **axis_style)
    # Axes TSS bars (secondary right — no labels)
    fig.update_yaxes(
        secondary_y=True,
        row=1,
        col=1,
        showgrid=False,
        zeroline=False,
        showline=False,
        showticklabels=False,
    )
    # Axes TSB (bottom panel)
    fig.update_yaxes(row=2, col=1, range=[-50, 30], **axis_style)
    # X axes
    fig.update_xaxes(
        row=1, col=1, showgrid=False, zeroline=False, showticklabels=False, showline=False
    )
    fig.update_xaxes(row=2, col=1, **xaxis_style)

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_macro_cycle() -> None:
    today = today_local()
    rows = []
    for p in _macro_cycle():
        status = _phase_status(p["Début"], p["Fin"])
        if status == "EN COURS":
            days = (datetime.date.fromisoformat(p["Fin"]) - today).days
            days_txt = f"{days}j"
            vs = f"color:{PALETTE['amber']};font-weight:500"
            dot = f'<span style="color:{PALETTE["amber"]}">&#9679;</span>'
        elif status == "PASSÉ":
            days_txt = ""
            vs = f"color:{GRAY};opacity:.45"
            dot = f'<span style="color:{GRAY}">&#9675;</span>'
        else:
            days_txt = ""
            vs = f"color:{PALETTE['sky_blue']};opacity:.65"
            dot = f'<span style="color:{PALETTE["blue_green"]}">&#9676;</span>'

        rows.append(
            f'<tr style="border-bottom:1px solid {CHART_COLORS["table_border"]}">'
            f'<td style="{vs};padding:3px 10px;font-size:.7rem;white-space:nowrap">'
            f"{dot}&nbsp;{p['Phase']}</td>"
            f'<td style="{vs};padding:3px 8px;font-size:.68rem">{p["Focus"]}</td>'
            f'<td style="padding:3px 8px;font-size:.65rem;color:{GRAY};text-align:right;'
            f'white-space:nowrap">{p["Début"][:7]}&nbsp;{days_txt}</td>'
            f"</tr>"
        )

    st.markdown(
        '<table style="width:100%;border-collapse:collapse">' + "".join(rows) + "</table>",
        unsafe_allow_html=True,
    )
