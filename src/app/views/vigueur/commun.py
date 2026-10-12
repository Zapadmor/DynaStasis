"""Données de profil, formats et gabarits partagés par les onglets."""

from __future__ import annotations

import streamlit as st

from src.app.components import (
    GRAY,
    PALETTE,
    TRANSPARENT,
    VIGUEUR_COLORS,
)
from src.core.profile import get_profile
from src.core.tz import today_local
from src.services import vigueur

# ─────────────────────────────────────────────────────────────────────────────
# DONNÉES STATIQUES
# ─────────────────────────────────────────────────────────────────────────────


def _macro_cycle() -> list[dict]:
    """Phases d'entraînement (clé `vigueur.macro_cycle` : liste de {Phase, Début, Fin, Focus})."""
    return get_profile("vigueur.macro_cycle", []) or []


def _vo2max_actuel() -> float | None:
    return get_profile("vigueur.vo2max_actuel")


def _latest(df, col: str):
    if df is None or df.empty or col not in df.columns:
        return None
    vals = df[col].dropna()
    return float(vals.iloc[-1]) if not vals.empty else None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _phase_status(start: str, end: str) -> str:
    return vigueur.statut_phase(start, end, today_local())


def _fmt(v, decimals: int = 1, suffix: str = "") -> str:
    if v is None:
        return "—"
    return f"{int(round(v))}{suffix}" if decimals == 0 else f"{v:.{decimals}f}{suffix}"


_COULEURS_FORME = {
    "—": GRAY,
    "SURMENAGE": PALETTE["tiger"],
    "OPTIMAL": VIGUEUR_COLORS["optimal"],
    "ZONE GRISE": GRAY,
    "FRESH": VIGUEUR_COLORS["fresh"],
    "TRANSITION": PALETTE["sky_blue"],
}


def _form_status(tsb) -> tuple[str, str]:
    label = vigueur.statut_forme(tsb)
    return label, _COULEURS_FORME[label]


def _kpi_html(label: str, value: str, sub: str = "", color: str | None = None) -> str:
    c = color or PALETTE["sky_blue"]
    sub_line = (
        f'<div style="font-size:.58rem;color:{PALETTE["blue_green"]};margin-top:2px">{sub}</div>'
        if sub
        else ""
    )
    return (
        f'<div style="text-align:center;padding:8px 2px 4px;flex:1;min-width:0">'
        f'<div style="font-size:1.8rem;font-weight:200;color:{c};line-height:1">{value}</div>'
        f'<div style="font-size:.6rem;font-weight:300;color:{PALETTE["sky_blue"]};'
        f'letter-spacing:.12em;text-transform:uppercase;margin-top:3px">{label}</div>'
        f"{sub_line}"
        f"</div>"
    )


def _base_layout(height: int = 160) -> dict:
    return dict(
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font_family="Satoshi",
        font_color=PALETTE["sky_blue"],
        font_size=9,
        showlegend=False,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showline=True,
            linecolor=PALETTE["blue_green"],
            linewidth=1,
            tickfont=dict(size=8),
        ),
        yaxis=dict(showgrid=False, zeroline=False, showline=False, tickfont=dict(size=8)),
        height=height,
        margin=dict(l=4, r=4, t=8, b=24),
    )


def _empty_chart(height: int = 110) -> None:
    st.markdown(
        f'<div style="height:{height}px;display:flex;align-items:center;'
        f"justify-content:center;font-size:.6rem;color:{GRAY};"
        f'letter-spacing:.08em">SYNC REQUIS</div>',
        unsafe_allow_html=True,
    )
