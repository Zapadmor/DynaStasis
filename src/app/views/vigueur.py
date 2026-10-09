from __future__ import annotations

import datetime

import streamlit as st
import streamlit.components.v1 as _st_components

from src.app.components import (
    CHART_COLORS,
    GRAY,
    PALETTE,
    SCREEN_APP_COLORS,
    TRANSPARENT,
    VIGUEUR_COLORS,
)
from src.collectors.workout_db import (
    compute_load,
    create_session,
    delete_session,
    finish_session,
    get_exercise_performance,
    get_exercises,
    get_session_detail,
    get_sessions,
    get_template_detail,
    get_templates,
    save_session_exercises,
    sync_intervals_workout_links,
    update_template_from_session,
)
from src.core.profile import get_profile
from src.core.tz import today_local
from src.database.connection import db_session

# ─────────────────────────────────────────────────────────────────────────────
# DONNÉES STATIQUES
# ─────────────────────────────────────────────────────────────────────────────


def _macro_cycle() -> list[dict]:
    """Phases d'entraînement (clé `vigueur.macro_cycle` : liste de {Phase, Début, Fin, Focus})."""
    return get_profile("vigueur.macro_cycle", []) or []


def _vo2max_actuel() -> float | None:
    return get_profile("vigueur.vo2max_actuel")


# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────


def _load_data() -> tuple:
    try:
        import pandas as pd
    except ImportError:
        return None, None, None

    try:
        with db_session() as conn:
            rows_w = conn.execute(
                "SELECT * FROM v_vigueur_hebdo ORDER BY week_start DESC LIMIT 26"
            ).fetchall()
            rows_d = conn.execute(
                """SELECT date_entry, hrv, rhr, sleep_min, steps, ctl, atl, tsb
                   FROM vigueur_entries ORDER BY date_entry DESC LIMIT 7"""
            ).fetchall()
            rows_daily = conn.execute(
                """SELECT date_entry, ctl, atl, tsb, tss
                   FROM vigueur_entries WHERE ctl IS NOT NULL
                   ORDER BY date_entry ASC"""
            ).fetchall()
    except Exception:
        import pandas as pd

        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    import pandas as pd

    df_w = (
        pd.DataFrame([dict(r) for r in rows_w]).sort_values("week_start")
        if rows_w
        else pd.DataFrame()
    )
    df_d = (
        pd.DataFrame([dict(r) for r in rows_d]).sort_values("date_entry")
        if rows_d
        else pd.DataFrame()
    )
    df_daily = pd.DataFrame([dict(r) for r in rows_daily]) if rows_daily else pd.DataFrame()
    return df_w, df_d, df_daily


def _latest(df, col: str):
    if df is None or df.empty or col not in df.columns:
        return None
    vals = df[col].dropna()
    return float(vals.iloc[-1]) if not vals.empty else None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _phase_status(start: str, end: str) -> str:
    today = today_local()
    if today < datetime.date.fromisoformat(start):
        return "À VENIR"
    if today > datetime.date.fromisoformat(end):
        return "PASSÉ"
    return "EN COURS"


def _fmt(v, decimals: int = 1, suffix: str = "") -> str:
    if v is None:
        return "—"
    return f"{int(round(v))}{suffix}" if decimals == 0 else f"{v:.{decimals}f}{suffix}"


def _form_status(tsb) -> tuple[str, str]:
    if tsb is None:
        return "—", GRAY
    if tsb < -30:
        return "SURMENAGE", PALETTE["tiger"]
    if tsb < -10:
        return "OPTIMAL", VIGUEUR_COLORS["optimal"]
    if tsb < 5:
        return "ZONE GRISE", GRAY
    if tsb < 20:
        return "FRESH", VIGUEUR_COLORS["fresh"]
    return "TRANSITION", PALETTE["sky_blue"]


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

    tsb_color = (
        PALETTE["tiger"]
        if (tsb or 0) < -30
        else VIGUEUR_COLORS["optimal"]
        if (tsb or 0) < -10
        else GRAY
        if (tsb or 0) < 5
        else VIGUEUR_COLORS["fresh"]
        if (tsb or 0) < 20
        else PALETTE["sky_blue"]
    )

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


def _mini_bars(df, col: str, color: str, height: int = 110) -> None:
    import plotly.graph_objects as go

    if df is None or df.empty or col not in df.columns or df[col].isna().all():
        _empty_chart(height)
        return

    labels = (
        [d[-5:] for d in df["date_entry"]] if "date_entry" in df.columns else list(range(len(df)))
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
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_screen_bars(height: int = 110) -> None:
    """Stacked horizontal bar — top 5 apps, 7 derniers jours. Sans légende."""
    import plotly.graph_objects as go

    try:
        with db_session() as conn:
            rows = conn.execute("""
                SELECT app_name, ROUND(SUM(duration_seconds) / 60.0, 1) AS minutes
                FROM screen_sessions
                WHERE session_start >= datetime('now', '-7 days')
                GROUP BY app_name
                ORDER BY minutes DESC
                LIMIT 5
            """).fetchall()
    except Exception:
        _empty_chart(height)
        return

    if not rows:
        _empty_chart(height)
        return

    fig = go.Figure()
    for i, row in enumerate(rows):
        name, mins = row[0], row[1]
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
                    x=[d[-5:] for d in last7["week_start"]],
                    y=last7["distance_km"],
                    marker_color=PALETTE["blue_green"],
                    marker_line_width=0,
                )
            )
            fig.update_layout(**_base_layout(110))
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
        try:
            with db_session() as conn:
                total_row = conn.execute("""
                    SELECT ROUND(SUM(duration_seconds) / 3600.0, 1)
                    FROM screen_sessions
                    WHERE session_start >= datetime('now', '-7 days')
                """).fetchone()
            total_h = total_row[0] if total_row and total_row[0] else None
        except Exception:
            total_h = None
        total_str = f"{total_h}h" if total_h else "—"
        st.markdown(
            _kpi_html("Écran 7j", total_str, "top apps", PALETTE["tiger"]),
            unsafe_allow_html=True,
        )
        _render_screen_bars()


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


# ─────────────────────────────────────────────────────────────────────────────
# TAB — LOG WORKOUTS
# ─────────────────────────────────────────────────────────────────────────────

_EMOM_TIMER_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: transparent; font-family: Satoshi, sans-serif; padding: 6px 0; }}
  #label {{ font-size: .6rem; letter-spacing: .12em; text-transform: uppercase;
             opacity: .55; margin-bottom: 4px; }}
  #wrap {{ display: flex; align-items: center; gap: 10px; }}
  #ring {{ position: relative; width: 64px; height: 64px; flex-shrink: 0; }}
  #ring svg {{ position: absolute; top: 0; left: 0; transform: rotate(-90deg); }}
  #ring-bg {{ fill: none; stroke: #ffffff22; stroke-width: 4; }}
  #ring-fg {{ fill: none; stroke: #ffb703; stroke-width: 4;
               stroke-linecap: round;
               stroke-dasharray: {circ};
               stroke-dashoffset: 0;
               transition: stroke-dashoffset .9s linear, stroke .3s; }}
  #ring-fg.urgent {{ stroke: #e63946; }}
  #digits {{ position: absolute; inset: 0; display: flex; align-items: center;
              justify-content: center;
              font-size: 1.05rem; font-weight: 200; color: #ffb703; }}
  #digits.urgent {{ color: #e63946; }}
  .btn {{ padding: 5px 14px; border: 1px solid #ffffff44; border-radius: 20px;
           background: transparent; color: #eee; cursor: pointer;
           font-size: .72rem; letter-spacing: .06em;
           transition: background .15s, border-color .15s; }}
  .btn:hover {{ background: #ffffff18; border-color: #ffffff88; }}
  #startBtn {{ min-width: 68px; text-align: center; }}
</style>
</head>
<body>
<div id="label">EMOM — {interval} s / série</div>
<div id="wrap">
  <div id="ring">
    <svg width="64" height="64" viewBox="0 0 64 64">
      <circle id="ring-bg" cx="32" cy="32" r="{r}"/>
      <circle id="ring-fg" cx="32" cy="32" r="{r}"/>
    </svg>
    <div id="digits">1:00</div>
  </div>
  <button class="btn" id="startBtn" onclick="toggle()">▶ Start</button>
  <button class="btn" onclick="reset()">↺ Reset</button>
</div>
<script>
const INTERVAL = {interval};
const CIRC = {circ};
let remaining = INTERVAL;
let running = false;
let tick = null;
let ctx = null;

function beep() {{
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
  const osc = ctx.createOscillator();
  const g   = ctx.createGain();
  osc.connect(g); g.connect(ctx.destination);
  osc.frequency.value = 880; osc.type = 'sine';
  g.gain.setValueAtTime(0.45, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
  osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.45);
}}

function draw() {{
  const pct = remaining / INTERVAL;
  const offset = CIRC * (1 - pct);
  const fg = document.getElementById('ring-fg');
  const dg = document.getElementById('digits');
  fg.style.strokeDashoffset = offset;
  const urgent = remaining <= 5;
  fg.className = urgent ? 'urgent' : '';
  dg.className = urgent ? 'urgent' : '';
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  dg.textContent = m + ':' + String(s).padStart(2,'0');
}}

function toggle() {{
  if (running) {{
    clearInterval(tick); running = false;
    document.getElementById('startBtn').textContent = '▶ Start';
  }} else {{
    running = true;
    document.getElementById('startBtn').textContent = '⏸ Pause';
    tick = setInterval(() => {{
      remaining--;
      draw();
      if (remaining <= 0) {{
        beep();
        remaining = INTERVAL;
        draw();
      }}
    }}, 1000);
  }}
}}

function reset() {{
  clearInterval(tick); running = false; remaining = INTERVAL;
  document.getElementById('startBtn').textContent = '▶ Start';
  draw();
}}

draw();
</script>
</body>
</html>"""


def _render_emom_timer(interval_sec: int) -> None:
    import math

    r = 28
    circ = round(2 * math.pi * r, 2)
    html = _EMOM_TIMER_HTML.format(interval=interval_sec, r=r, circ=circ)
    _st_components.html(html, height=90)


# CSS : dimme les lignes de séries non cochées via :has()
_WORKOUT_CSS = """
<style>
[data-testid="stHorizontalBlock"]:has([data-testid="stCheckbox"] input:not(:checked)) {
    opacity: 0.38;
    transition: opacity 0.15s;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stCheckbox"] input:checked) {
    opacity: 1;
    transition: opacity 0.15s;
}
</style>
"""


def _tab_log_workouts() -> None:
    today = today_local().isoformat()

    active_key = "workout_active_session_id"
    exercises_key = "workout_exercises"
    bw_key = "workout_bodyweight"
    finished_key = "workout_just_finished"
    confirm_finish_key = "workout_confirm_finish"
    confirm_delete_key = "workout_confirm_delete_id"
    editing_key = "workout_editing_mode"
    phone_key = "workout_phone_mode"

    for k, v in [
        (active_key, None),
        (exercises_key, []),
        (bw_key, 0.0),
        (finished_key, None),
        (confirm_finish_key, False),
        (confirm_delete_key, None),
        (editing_key, False),
        (phone_key, False),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    phone_mode: bool = st.session_state[phone_key]
    phone_label = "MODE TELEPHONE  ON" if phone_mode else "MODE TELEPHONE"
    if st.button(phone_label, key="workout_phone_toggle"):
        st.session_state[phone_key] = not phone_mode
        st.rerun()

    sessions = get_sessions(limit=20)
    finished = [s for s in sessions if s["finished_at"]]

    if st.session_state[active_key] is None:
        # ── Confirmation suppression ──────────────────────────────────────
        del_id = st.session_state[confirm_delete_key]
        if del_id is not None:
            target = next((s for s in finished if s["id"] == del_id), None)
            label = target["date_entry"] if target else str(del_id)
            st.warning(f"Supprimer la séance du **{label}** ? Cette action est irréversible.")
            dc1, dc2 = st.columns([1, 1])
            with dc1:
                if st.button("Confirmer la suppression", key="workout_del_confirm", type="primary"):
                    delete_session(del_id)
                    st.session_state[confirm_delete_key] = None
                    st.rerun()
            with dc2:
                if st.button("Annuler", key="workout_del_cancel"):
                    st.session_state[confirm_delete_key] = None
                    st.rerun()
            st.markdown("---")

        # ── Proposition mise à jour template post-séance ──────────────────
        if st.session_state[finished_key] is not None:
            info = st.session_state[finished_key]
            st.info(f"Séance **{info['name']}** terminée — Volume : **{info['volume']} kg·reps**")
            if info.get("template_id"):
                if st.button(
                    "Mettre à jour le template avec ces performances",
                    key="workout_update_tmpl",
                ):
                    update_template_from_session(info["session_id"])
                    st.success("Template mis à jour !")
                    st.session_state[finished_key] = None
                    st.rerun()
                if st.button("Ignorer", key="workout_ignore_tmpl"):
                    st.session_state[finished_key] = None
                    st.rerun()
            else:
                st.session_state[finished_key] = None
            st.markdown("---")

        _render_new_session_form(today, active_key, exercises_key, bw_key, editing_key, phone_mode)
        if finished:
            st.markdown("---")
            _render_history(
                finished,
                active_key,
                exercises_key,
                bw_key,
                editing_key,
                confirm_delete_key,
            )
    else:
        st.markdown(_WORKOUT_CSS, unsafe_allow_html=True)
        _render_active_session(
            active_key,
            exercises_key,
            bw_key,
            finished_key,
            confirm_finish_key,
            editing_key,
        )


def _render_new_session_form(
    today: str,
    active_key: str,
    exercises_key: str,
    bw_key: str,
    editing_key: str,
    phone_mode: bool = False,
) -> None:
    st.subheader("Nouvelle séance")

    templates = get_templates()
    tmpl_names = [t["name"] for t in templates]
    tmpl_ids = {t["name"]: t["id"] for t in templates}

    if phone_mode:
        chosen = st.selectbox("Template", tmpl_names, key="workout_tmpl_select")
        date_col, bw_col = st.columns([1, 1])
        with date_col:
            date_str = st.date_input(
                "Date", value=datetime.date.fromisoformat(today), key="workout_date_pick"
            ).isoformat()
        with bw_col:
            bw = st.number_input(
                "Poids (kg)",
                min_value=0.0,
                step=0.5,
                value=float(st.session_state.get(bw_key) or 67.0),
                key="workout_bw_input",
            )
    else:
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            chosen = st.selectbox("Template", tmpl_names, key="workout_tmpl_select")
        with col2:
            date_str = st.date_input(
                "Date", value=datetime.date.fromisoformat(today), key="workout_date_pick"
            ).isoformat()
        with col3:
            bw = st.number_input(
                "Poids de corps (kg)",
                min_value=0.0,
                step=0.5,
                value=float(st.session_state.get(bw_key) or 67.0),
                key="workout_bw_input",
            )

    if st.button("Démarrer la séance", type="primary"):
        tmpl_id = tmpl_ids.get(chosen)
        st.session_state[bw_key] = bw
        session_id = create_session(date_str, tmpl_id, chosen, bodyweight_kg=bw)
        st.session_state[active_key] = session_id
        st.session_state[editing_key] = False

        detail = get_template_detail(tmpl_id)
        exercises = []
        for ex in detail.get("exercises", []):
            exercises.append(
                {
                    "exercise_id": ex["exercise_id"],
                    "name": ex["name"],
                    "position": ex["position"],
                    "load_formula": ex["load_formula"],
                    "emom_interval_sec": ex.get("emom_interval_sec"),
                    "sets": [
                        {
                            "set_type": s["set_type"],
                            "weight_kg": float(s["weight_kg"]),
                            "reps": int(s["reps"]),
                            "completed": False,
                        }
                        for s in ex["sets"]
                    ],
                }
            )
        st.session_state[exercises_key] = exercises
        st.rerun()


def _render_active_session(
    active_key: str,
    exercises_key: str,
    bw_key: str,
    finished_key: str,
    confirm_finish_key: str,
    editing_key: str,
) -> None:
    session_id: int = st.session_state[active_key]
    exercises: list[dict] = st.session_state[exercises_key]
    bw = float(st.session_state.get(bw_key) or 0.0)
    is_editing = st.session_state.get(editing_key, False)

    st.subheader("Modification de la séance" if is_editing else "Séance en cours")

    all_ex = get_exercises()
    ex_names = [e["name"] for e in all_ex]
    ex_map = {e["name"]: e for e in all_ex}

    to_delete_ex: int | None = None
    move_up: int | None = None
    move_down: int | None = None
    to_delete_set: tuple[int, int] | None = None

    for i, ex in enumerate(exercises):
        formula = ex.get("load_formula", "weight")
        done_sets = [s for s in ex["sets"] if s.get("completed")]
        vol_ex = sum(compute_load(s["weight_kg"], formula, bw) * s["reps"] for s in done_sets)
        label_suffix = f"  —  {len(done_sets)}/{len(ex['sets'])} séries" + (
            f"  ·  {vol_ex:.0f} kg·reps" if vol_ex else ""
        )

        with st.expander(f"{i + 1}. {ex['name']}{label_suffix}", expanded=True):
            col_up, col_down, col_del = st.columns([1, 1, 6])
            with col_up:
                if st.button("↑", key=f"ex_up_{i}", disabled=(i == 0)):
                    move_up = i
            with col_down:
                if st.button("↓", key=f"ex_down_{i}", disabled=(i == len(exercises) - 1)):
                    move_down = i
            with col_del:
                if st.button("Supprimer l'exercice", key=f"ex_del_{i}"):
                    to_delete_ex = i

            # ── Timer EMOM ───────────────────────────────────────────────
            emom_sec = ex.get("emom_interval_sec")
            if emom_sec:
                _render_emom_timer(emom_sec)

            # ── Séries — label = numéro, séries cochées masquées ─────────
            for j, s in enumerate(ex["sets"]):
                if s.get("completed"):
                    continue
                sc0, sc1, sc2, sc3 = st.columns([1, 3, 2, 1])
                with sc0:
                    done = st.checkbox(
                        s["set_type"],
                        value=False,
                        key=f"done_{i}_{j}",
                    )
                    if done:
                        s["completed"] = True
                with sc1:
                    new_weight = st.number_input(
                        "Poids (kg)",
                        min_value=0.0,
                        step=2.5,
                        value=float(s["weight_kg"]),
                        key=f"weight_{i}_{j}",
                        label_visibility="collapsed",
                    )
                    if new_weight != s["weight_kg"]:
                        _propagate_to_pending(ex["sets"], j, "weight_kg", new_weight, "weight", i)
                    s["weight_kg"] = new_weight
                with sc2:
                    new_reps = st.number_input(
                        "Reps",
                        min_value=1,
                        step=1,
                        value=int(s["reps"]),
                        key=f"reps_{i}_{j}",
                        label_visibility="collapsed",
                    )
                    if new_reps != s["reps"]:
                        _propagate_to_pending(ex["sets"], j, "reps", new_reps, "reps", i)
                    s["reps"] = new_reps
                with sc3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🗑", key=f"del_set_{i}_{j}", help="Supprimer cette série"):
                        to_delete_set = (i, j)

            _renumber_sets(ex["sets"])

            if st.button("+ Série", key=f"add_set_{i}"):
                working_count = sum(1 for s in ex["sets"] if s["set_type"] not in ("W", "F"))
                ex["sets"].append(
                    {
                        "set_type": str(working_count + 1),
                        "weight_kg": ex["sets"][-1]["weight_kg"] if ex["sets"] else 0.0,
                        "reps": ex["sets"][-1]["reps"] if ex["sets"] else 5,
                        "completed": False,
                    }
                )
                st.rerun()

    if move_up is not None:
        exercises[move_up], exercises[move_up - 1] = (
            exercises[move_up - 1],
            exercises[move_up],
        )
        _reposition(exercises)
        st.rerun()
    if move_down is not None:
        exercises[move_down], exercises[move_down + 1] = (
            exercises[move_down + 1],
            exercises[move_down],
        )
        _reposition(exercises)
        st.rerun()
    if to_delete_ex is not None:
        exercises.pop(to_delete_ex)
        _reposition(exercises)
        st.rerun()
    if to_delete_set is not None:
        ex_idx, set_idx = to_delete_set
        sets_list = exercises[ex_idx]["sets"]
        old_len = len(sets_list)
        sets_list.pop(set_idx)
        # Les clés de widgets sont indexées par position : après suppression,
        # les positions décalées doivent perdre leur ancien état en session
        # pour ne pas afficher les valeurs de la série voisine.
        for k in range(set_idx, old_len):
            for prefix in ("done", "weight", "reps"):
                st.session_state.pop(f"{prefix}_{ex_idx}_{k}", None)
        _renumber_sets(sets_list)
        st.rerun()

    # ── Ajouter exercice ──────────────────────────────────────────────────────
    st.markdown("---")
    add_col1, add_col2 = st.columns([4, 1])
    with add_col1:
        new_ex_name = st.selectbox(
            "Ajouter un exercice",
            ["— choisir —"] + ex_names,
            key="workout_add_ex_select",
        )
    with add_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Ajouter", key="workout_add_ex_btn") and new_ex_name != "— choisir —":
            ex_info = ex_map[new_ex_name]
            exercises.append(
                {
                    "exercise_id": ex_info["id"],
                    "name": new_ex_name,
                    "position": len(exercises) + 1,
                    "load_formula": ex_info.get("load_formula", "weight"),
                    "sets": [{"set_type": "1", "weight_kg": 0.0, "reps": 5, "completed": False}],
                }
            )
            st.rerun()

    # ── Volume total ──────────────────────────────────────────────────────────
    total_vol = sum(
        compute_load(s["weight_kg"], ex.get("load_formula", "weight"), bw) * s["reps"]
        for ex in exercises
        for s in ex["sets"]
        if s.get("completed")
    )
    nb_done = sum(1 for ex in exercises for s in ex["sets"] if s.get("completed"))
    st.markdown("---")
    st.metric(
        "Volume effectué",
        f"{total_vol:.0f} kg·reps",
        help="Somme de charge × reps pour toutes les séries cochées",
        delta=f"{nb_done} série{'s' if nb_done != 1 else ''} effectuée{'s' if nb_done != 1 else ''}",
    )

    # ── Actions finales ───────────────────────────────────────────────────────
    nb_total = sum(len(ex["sets"]) for ex in exercises)
    nb_done = sum(1 for ex in exercises for s in ex["sets"] if s.get("completed"))
    has_incomplete = nb_done < nb_total

    # ── Confirmation séries incomplètes ───────────────────────────────────────
    if st.session_state.get(confirm_finish_key):
        st.warning(
            f"**{nb_total - nb_done} série(s) non effectuée(s)** ne seront pas sauvegardées. "
            "Êtes-vous sûr de vouloir jeter les séries inachevées ?"
        )
        cf1, cf2 = st.columns([1, 1])
        with cf1:
            if st.button("Oui, terminer quand même", key="workout_confirm_yes", type="primary"):
                st.session_state[confirm_finish_key] = False
                _do_finish_session(
                    session_id, exercises, bw, active_key, exercises_key, finished_key, editing_key
                )
        with cf2:
            if st.button("Non, continuer la séance", key="workout_confirm_no"):
                st.session_state[confirm_finish_key] = False
                st.rerun()
    else:
        finish_label = "Enregistrer les modifications" if is_editing else "Terminer la séance"
        finish_col, cancel_col = st.columns([2, 1])
        with finish_col:
            if st.button(finish_label, type="primary", key="workout_finish"):
                if has_incomplete and not is_editing:
                    st.session_state[confirm_finish_key] = True
                    st.rerun()
                else:
                    _do_finish_session(
                        session_id,
                        exercises,
                        bw,
                        active_key,
                        exercises_key,
                        finished_key,
                        editing_key,
                    )
        with cancel_col:
            if st.button("Annuler", key="workout_cancel"):
                st.session_state[active_key] = None
                st.session_state[exercises_key] = []
                st.session_state[finished_key] = None
                st.session_state[editing_key] = False
                st.rerun()


def _do_finish_session(
    session_id: int,
    exercises: list[dict],
    bw: float,
    active_key: str,
    exercises_key: str,
    finished_key: str,
    editing_key: str,
) -> None:
    # Garder uniquement les séries effectuées
    exercises_to_save = []
    for ex in exercises:
        done_sets = [s for s in ex["sets"] if s.get("completed")]
        if done_sets:
            exercises_to_save.append({**ex, "sets": done_sets})

    save_session_exercises(session_id, exercises_to_save, bodyweight_kg=bw)
    finish_session(session_id, bodyweight_kg=bw)

    with db_session() as conn:
        row = conn.execute(
            "SELECT name, template_id, session_volume_kg FROM workout_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    st.session_state[finished_key] = {
        "session_id": session_id,
        "name": row["name"] if row else "Séance",
        "template_id": row["template_id"] if row else None,
        "volume": round(row["session_volume_kg"] or 0, 0) if row else 0,
    }
    st.session_state[active_key] = None
    st.session_state[exercises_key] = []
    st.session_state[editing_key] = False
    st.rerun()


def _render_history(
    sessions: list[dict],
    active_key: str,
    exercises_key: str,
    bw_key: str,
    editing_key: str,
    confirm_delete_key: str,
) -> None:
    show_key = "workout_show_history"
    if show_key not in st.session_state:
        st.session_state[show_key] = False

    n = len(sessions)
    is_open = st.session_state[show_key]
    arrow = "▾" if is_open else "▸"
    hdr_col, sync_col = st.columns([5, 2])
    with hdr_col:
        if st.button(
            f"HISTORIQUE  ({n})  {arrow}",
            key="workout_hist_toggle",
        ):
            st.session_state[show_key] = not is_open
            st.rerun()
    with sync_col:
        if st.button("Sync Intervals (30 j)", key="workout_sync_intervals"):
            try:
                from src.collectors.intervals_client import IntervalsClient

                client = IntervalsClient()
                activities = client.get_activities(lookback_days=30)
                n_linked = sync_intervals_workout_links(activities)
                if n_linked:
                    st.success(f"{n_linked} séance(s) liée(s) à Intervals.")
                else:
                    st.info("Aucune nouvelle liaison trouvée.")
                st.rerun()
            except Exception as exc:
                st.error(f"Erreur Intervals.icu : {exc}")

    if not st.session_state[show_key]:
        return

    def _load_and_edit(session_id: int) -> None:
        detail = get_session_detail(session_id)
        exercises = []
        for ex in detail.get("exercises", []):
            exercises.append(
                {
                    "exercise_id": ex["exercise_id"],
                    "name": ex["name"],
                    "position": ex["position"],
                    "load_formula": ex.get("load_formula", "weight"),
                    "emom_interval_sec": ex.get("emom_interval_sec"),
                    "sets": [
                        {
                            "set_type": sv["set_type"],
                            "weight_kg": float(sv["weight_kg"]),
                            "reps": int(sv["reps"]),
                            "completed": bool(sv["completed"]),
                        }
                        for sv in ex["sets"]
                    ],
                }
            )
        st.session_state[exercises_key] = exercises
        st.session_state[bw_key] = detail.get("bodyweight_kg") or 67.0
        st.session_state[active_key] = session_id
        st.session_state[editing_key] = True
        st.rerun()

    for s in sessions:
        duration = ""
        if s.get("started_at") and s.get("finished_at"):
            try:
                start = datetime.datetime.fromisoformat(s["started_at"])
                end = datetime.datetime.fromisoformat(s["finished_at"])
                mins = int((end - start).total_seconds() / 60)
                duration = f" · {mins} min"
            except ValueError:
                pass
        volume = f" · {s['session_volume_kg']:.0f} kg·reps" if s.get("session_volume_kg") else ""
        intervals_badge = " · Intervals" if s.get("intervals_activity_id") else ""

        info_col, btn_edit, btn_del = st.columns([6, 1, 1])
        with info_col:
            st.markdown(
                f"**{s['date_entry']}** — {s['name']}"
                f" · {s['nb_exercises']} exos"
                f" · {s['nb_completed']}/{s['nb_sets']} séries{duration}{volume}{intervals_badge}"
            )
        with btn_edit:
            if st.button("Mod", key=f"hist_edit_{s['id']}", help="Modifier"):
                _load_and_edit(s["id"])
        with btn_del:
            if st.button("Del", key=f"hist_del_{s['id']}", help="Supprimer"):
                st.session_state[confirm_delete_key] = s["id"]
                st.rerun()


def _propagate_to_pending(
    sets: list[dict], from_index: int, field: str, value, key_prefix: str, ex_idx: int
) -> None:
    """Reporte weight_kg/reps saisis sur une série vers toutes les séries
    suivantes non encore complétées (saisie manuelle différée — copie la
    valeur, la validation par checkbox reste manuelle pour chaque série)."""
    for k in range(from_index + 1, len(sets)):
        if sets[k].get("completed"):
            continue
        sets[k][field] = value
        st.session_state[f"{key_prefix}_{ex_idx}_{k}"] = value


def _renumber_sets(sets: list[dict]) -> None:
    counter = 1
    for s in sets:
        if s["set_type"] not in ("W", "F"):
            s["set_type"] = str(counter)
            counter += 1


def _reposition(exercises: list[dict]) -> None:
    for i, ex in enumerate(exercises):
        ex["position"] = i + 1
