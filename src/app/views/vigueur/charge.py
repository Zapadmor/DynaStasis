"""Onglet « Charge & Récupération » : courbe CTL/ATL/TSB avec les pauses, macro-cycle et jalons."""

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
from src.app.views.vigueur.commun import _macro_cycle, _macro_cycle_objectif, _phase_status
from src.core.tz import today_local
from src.services import objectifs as objectifs_service
from src.services import vigueur

# ─────────────────────────────────────────────────────────────────────────────
# DONNÉES
# ─────────────────────────────────────────────────────────────────────────────


def _load_data():
    try:
        import pandas as pd
    except ImportError:
        return None
    return pd.DataFrame(vigueur.charge_quotidienne())


# ─────────────────────────────────────────────────────────────────────────────
# COURBE DE CHARGE ET PAUSES
# ─────────────────────────────────────────────────────────────────────────────

_RANGE_DAYS = {"1S": 7, "1M": 30, "3M": 91, "6M": 182, "1A": 365, "TOUT": 9999}

_TSB_ZONES = [
    # (y0, y1, fill_color, label, label_color)
    (20, 200, CHART_COLORS["tsb_transition_fill"], "TRANSITION", GRAY),
    (5, 20, CHART_COLORS["tsb_fresh_fill"], "FRESH", VIGUEUR_COLORS["fresh"]),
    (-10, 5, CHART_COLORS["tsb_grey_fill"], "GREY ZONE", GRAY),
    (-30, -10, CHART_COLORS["tsb_optimal_fill"], "OPTIMAL", VIGUEUR_COLORS["optimal"]),
    (-200, -30, CHART_COLORS["tsb_highrisk_fill"], "HIGH RISK", PALETTE["tiger"]),
]


def _milieu(x0: str, x1: str) -> str:
    d0, d1 = datetime.date.fromisoformat(x0), datetime.date.fromisoformat(x1)
    return (d0 + (d1 - d0) / 2).isoformat()


def _render_charge_chart(df_daily) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if df_daily is None or df_daily.empty:
        st.caption("Aucune donnée — lancez `python main.py vigueur`.")
        return

    # ── Sélecteur de période (query params pour partage URL) ──────
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

    has_tss = "tss" in df.columns and df["tss"].notna().any()

    # ── Figure à deux panneaux (secondary_y pour les barres TSS) ──
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.58, 0.42],
        vertical_spacing=0.02,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )

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

    # Panneau 2 : TSB / Form + zones
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

    # ── Pauses du système (gels) : bandes ambre sur les deux panneaux ──
    bandes = vigueur.bandes_pauses(vigueur.pauses(), df["date_entry"].min(), df["date_entry"].max())
    for b in bandes:
        for row in (1, 2):
            fig.add_vrect(
                x0=b["x0"],
                x1=b["x1"],
                fillcolor=PALETTE["amber"],
                opacity=0.22,
                line_width=0,
                layer="below",
                row=row,
                col=1,
            )
        fig.add_annotation(
            x=_milieu(b["x0"], b["x1"]),
            y=1,
            xref="x",
            yref="paper",
            yanchor="top",
            text=b["label"],
            showarrow=False,
            font=dict(size=10, color=PALETTE["amber"]),
        )
    if bandes:  # entrée de légende pour les bandes
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name="Pause du système",
                marker=dict(symbol="square", size=10, color=PALETTE["amber"], opacity=0.6),
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    # ── Mise en forme ─────────────────────────────────────────────
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
        height=340,
        margin=dict(l=36, r=10, t=28, b=10),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=9), bgcolor=TRANSPARENT
        ),
        bargap=0.1,
    )
    fig.update_yaxes(secondary_y=False, row=1, col=1, **axis_style)
    fig.update_yaxes(
        secondary_y=True,
        row=1,
        col=1,
        showgrid=False,
        zeroline=False,
        showline=False,
        showticklabels=False,
    )
    fig.update_yaxes(row=2, col=1, range=[-50, 30], **axis_style)
    fig.update_xaxes(
        row=1, col=1, showgrid=False, zeroline=False, showticklabels=False, showline=False
    )
    fig.update_xaxes(row=2, col=1, **xaxis_style)

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────────────────────────────────────
# MACRO-CYCLE ET JALONS (tâches de l'objectif Forge relié)
# ─────────────────────────────────────────────────────────────────────────────


def _fr(date_iso: str) -> str:
    return datetime.date.fromisoformat(date_iso[:10]).strftime("%d/%m/%Y")


def _titre_macro_cycle(phases: list[dict]) -> str:
    debut = min(p["Début"] for p in phases)[:4]
    fin = max(p["Fin"] for p in phases)[:4]
    return f"Macro-Cycle {debut}" if debut == fin else f"Macro-Cycle {debut}–{fin}"


def _render_phase(phase: dict) -> None:
    status = _phase_status(phase["Début"], phase["Fin"])
    if status == "EN COURS":
        jours = (datetime.date.fromisoformat(phase["Fin"]) - today_local()).days
        couleur, point, reste = PALETTE["amber"], "&#9679;", f" · {jours} j restants"
        opacite = 1
    elif status == "PASSÉ":
        couleur, point, reste, opacite = GRAY, "&#9675;", "", 0.55
    else:
        couleur, point, reste, opacite = PALETTE["sky_blue"], "&#9676;", "", 0.8
    st.markdown(
        f'<div style="margin-top:12px;padding-bottom:3px;opacity:{opacite};'
        f'border-bottom:1px solid {CHART_COLORS["table_border"]}">'
        f'<span style="color:{couleur};font-weight:600;font-size:.85rem">{point}&nbsp;{phase["Phase"]}</span>'
        f'<span style="font-size:.74rem;margin-left:10px">{phase["Focus"]}</span>'
        f'<div style="font-size:.64rem;color:{GRAY}">'
        f"{_fr(phase['Début'])} → {_fr(phase['Fin'])}{reste}</div></div>",
        unsafe_allow_html=True,
    )


def _render_jalon(tache: dict) -> None:
    """Jalon = tâche de l'objectif relié ; la case la valide, comme dans l'onglet Objectifs de Forge."""
    fait = tache["statut"] == "fait"
    c_case, c_texte = st.columns([1, 14])
    with c_case:
        coche = st.checkbox(
            tache["titre"], value=fait, key=f"jalon_{tache['id']}", label_visibility="collapsed"
        )
    if coche != fait:
        objectifs_service.cocher_tache(tache["id"], coche)
        st.rerun()
    with c_texte:
        barre = "text-decoration:line-through;opacity:.5;" if fait else ""
        echeance = (
            f'<span style="opacity:.5;font-size:.72rem"> · {_fr(tache["date_echeance"])}</span>'
            if tache.get("date_echeance")
            else ""
        )
        detail = (
            f'<div style="font-size:.68rem;color:{GRAY}">{tache["description"]}</div>'
            if tache.get("description")
            else ""
        )
        st.markdown(
            f'<div style="{barre}font-size:.82rem;padding:2px 0">{tache["titre"]}{echeance}{detail}</div>',
            unsafe_allow_html=True,
        )


def _render_macro_cycle() -> None:
    phases = _macro_cycle()
    if not phases:
        st.caption("Aucune phase de macro-cycle (contenu de profil `vigueur.macro_cycle`).")
        return

    objectif_id = _macro_cycle_objectif()
    taches = objectifs_service.charger_taches(objectif_id) if objectif_id is not None else []
    groupes, autres = vigueur.grouper_jalons(phases, taches)

    st.markdown(
        f'<div style="font-size:.62rem;font-weight:300;color:{PALETTE["blue_green"]};'
        f'letter-spacing:.15em;text-transform:uppercase;margin-bottom:4px">'
        f"{_titre_macro_cycle(phases)}</div>",
        unsafe_allow_html=True,
    )
    if taches:
        faits = sum(1 for t in taches if t["statut"] == "fait")
        st.progress(faits / len(taches), text=f"{faits} / {len(taches)} jalons validés")
    elif objectif_id is None:
        st.caption("Aucun objectif Forge relié (clé de profil `vigueur.macro_cycle_objectif`).")

    for phase, jalons in groupes:
        _render_phase(phase)
        for jalon in jalons:
            _render_jalon(jalon)
    if autres:
        st.markdown(
            f'<div style="margin-top:12px;font-size:.78rem;color:{GRAY}">Autres jalons</div>',
            unsafe_allow_html=True,
        )
        for jalon in autres:
            _render_jalon(jalon)
