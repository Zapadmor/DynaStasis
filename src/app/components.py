"""Composants réutilisables DynaStasie — sidebar, CSS, widgets.

Toutes les couleurs sont importées depuis src.styles (source unique de vérité).
La police Satoshi est définie dans static/custom.css (servi via config.toml staticFolderPath).
"""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from src.core.tz import today_local
from src.core.user_config import mode_label, pilier_actif, widget_url
from src.styles import (
    CHART_COLORS,
    GRAY,
    MODE_COLORS,
    PALETTE,
    RANK_COLORS,
    SCREEN_APP_COLORS,
    TRANSPARENT,
    TREEMAP_COLORS,
    VIGUEUR_COLORS,
    WHITE,
)

# Re-export pour que les vues puissent importer depuis un seul endroit.
__all__ = [
    "PALETTE",
    "RANK_COLORS",
    "VIGUEUR_COLORS",
    "MODE_COLORS",
    "TREEMAP_COLORS",
    "CHART_COLORS",
    "SCREEN_APP_COLORS",
    "GRAY",
    "WHITE",
    "TRANSPARENT",
    "inject_theme",
    "render_sidebar",
]


# ── Widget externe facultatif ─────────────────────────────────────────────────
def _widget_html(url: str) -> str:
    return (
        f'<iframe title="widget" src="{html.escape(url, quote=True)}" width="100%" height="190" '
        'frameborder="0" allowtransparency="true" allow="encrypted-media; clipboard-write">'
        "</iframe>"
    )


# ── Injection CSS / Police ────────────────────────────────────────────────────


def inject_theme() -> None:
    """Injecte static/custom.css — police Satoshi + surcharges typographiques."""
    css_path = Path(__file__).parent / "static" / "custom.css"
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ── Chrono Focus sidebar ──────────────────────────────────────────────────────


def _render_focus_sidebar(cw: dict | None) -> None:
    from src.core.focus_manager import (
        PILIERS,
        TAGS,
        get_active_session,
        get_week_pilier_breakdown,
        get_week_sessions,
        start_focus_session,
        stop_focus_session,
        tags_proposes,
    )

    st.markdown("**Chrono Focus**")
    active = get_active_session()
    if active:
        actifs = [TAGS[t][1] for t in (active.get("piliers") or "").split(",") if t in TAGS]
        tag_str = f" · {' + '.join(actifs)}" if actifs else ""
        st.warning(f"En cours · {active['heure_debut'][:5]}{tag_str}")
        if st.button("Stop", key="sb_stop_focus", use_container_width=True):
            _, msg = stop_focus_session()
            st.toast(msg)
            st.rerun()
    else:
        col_tag, col_btn = st.columns([3, 1])
        channel = col_tag.text_input(
            "Tag",
            value="code_local",
            key="sb_channel",
            label_visibility="collapsed",
            placeholder="Tag",
        )
        mode_actif = (cw or {}).get("mode_actif")
        tag_options = tags_proposes(mode_actif)
        piliers_sel = st.multiselect(
            "Pilier(s)",
            options=tag_options,
            format_func=lambda t: TAGS[t][1],
            key="sb_piliers",
            label_visibility="collapsed",
            placeholder="Pilier(s) — optionnel",
        )
        if col_btn.button("Go", key="sb_start_focus"):
            _, msg = start_focus_session(channel=channel, piliers=piliers_sel)
            st.toast(msg)
            st.rerun()

    if cw:
        sessions = get_week_sessions(cw["id"])
        if sessions:
            total = sum(s["duree_min"] or 0 for s in sessions)
            st.caption(f"Semaine : {total:.0f} min · {total / 60:.1f} h")
            if total:
                breakdown = get_week_pilier_breakdown(cw["id"])
                parts = [
                    f"{p.capitalize()} {breakdown[p] / total * 100:.0f}%"
                    for p in PILIERS
                    if breakdown[p] > 0 and pilier_actif(p)
                ]
                if parts:
                    st.caption("Répartition : " + " / ".join(parts))


# ── Cascade sync ─────────────────────────────────────────────────────────────


def _cascade_sync() -> None:
    """Recalcule les rollups semaines_audit depuis SQLite local (sans appel API).

    Les données externes (HRV, sleep, screen) sont rafraîchies par le timer
    systemd toutes les 6h — inutile de rappeler les APIs ici.
    """
    from src.core.system_engine import get_or_create_week_id, trigger_cascade_week

    date_str = today_local().isoformat()
    week_id = get_or_create_week_id(date_str)
    trigger_cascade_week(week_id)


# ── Log quotidien sidebar ─────────────────────────────────────────────────────


def _render_habit_sidebar() -> None:
    from src.core.habit_manager import upsert_habit_log
    from src.database.connection import db_session

    st.markdown("**Log du jour**")
    today_str = today_local().isoformat()

    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM habitude_logs WHERE date_log = ?", (today_str,)
        ).fetchone()
        rank_row = conn.execute(
            "SELECT rank FROM v_progression_quotidienne WHERE date_log = ?", (today_str,)
        ).fetchone()

    ex = dict(row) if row else {}
    rank = rank_row["rank"] if rank_row else None

    if rank:
        color = RANK_COLORS.get(rank, GRAY)
        st.markdown(
            f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:12px;font-size:.75rem;font-weight:700;">{rank}</span>',
            unsafe_allow_html=True,
        )

    _key = f"sb_habit_{today_str}"
    if _key not in st.session_state:
        st.session_state[_key] = True
        st.session_state["sb_hf_lecture"] = bool(ex.get("lecture_10min"))
        st.session_state["sb_hf_jeune"] = bool(ex.get("jeune_intermittent"))

    with st.form("sb_habit_form"):
        st.checkbox("Lecture", key="sb_hf_lecture")
        st.checkbox("Jeûne", key="sb_hf_jeune")
        if st.form_submit_button("Enregistrer", use_container_width=True):
            upsert_habit_log(
                today_str,
                lecture=st.session_state["sb_hf_lecture"],
                jeune=st.session_state["sb_hf_jeune"],
            )
            st.session_state.pop(_key, None)
            st.toast(f"Log {today_str} enregistré.")
            st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────


def render_sidebar(cw: dict | None) -> None:
    """Barre latérale : nav, métriques, chrono focus, log quotidien, Deezer."""
    with st.sidebar:
        st.title("DYNASTASIE")
        st.markdown("---")

        if cw:
            st.subheader(cw["week_label"])
            st.metric("Mode", mode_label(cw.get("mode_actif")))
        else:
            st.info("Aucune semaine active.")

        st.markdown("---")
        _render_focus_sidebar(cw)

        st.markdown("---")
        _render_habit_sidebar()

        st.markdown("---")
        st.caption(f"Aujourd'hui : {today_local().isoformat()}")

        if widget_url():
            st.markdown("---")
            st.markdown(_widget_html(widget_url()), unsafe_allow_html=True)
