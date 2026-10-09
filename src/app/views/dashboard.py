from __future__ import annotations

import datetime
import re
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

from src.app import theme as _theme
from src.app.components import CHART_COLORS, GRAY, MODE_COLORS, PALETTE, TRANSPARENT
from src.config import get_secret
from src.core import user_config
from src.core.tz import today_local, tz
from src.database.connection import db_session

# ── Pentagone ─────────────────────────────────────────────────────────────────

_N_WEEKS_MEDIAN = 4

_PILIER_QUERY = """
    SELECT ok_entrainement, ok_seances, ok_pas, ok_sommeil, ok_charge_fraicheur,
           ok_ecran, ok_deep_focus, ok_projets_fond, ok_engagement, ok_cloture
    FROM v_score_semaine
"""


# Modèle v2 (2026-08-31, cf. .github/PLAN_AUDIT_HEBDO_V2.md §8) : les 10 critères du score
# hebdo sont répartis sur les 4 pilliers du radar. ok_projets_fond compte pour FORGE et LOGOS
# (c'est littéralement le critère combiné "FORGE & LOGOS — Focus projets de fond").
# VIGUEUR = physique pur (5 critères) | FORGE = engagement + projets de fond
# LOGOS = deep focus contextuel + projets de fond | RÉSONNANCE = discipline écran + clôture audit
def _moyenne_criteres(r, criteres: list[str]) -> float | None:
    """% de critères validés parmi ceux qui sont actifs (poids > 0) ; None si aucun n'est actif."""
    actifs = [c for c in criteres if user_config.critere_actif(c)]
    if not actifs:
        return None
    return round(100.0 * sum(r[f"ok_{c}"] for c in actifs) / len(actifs), 1)


def _scores_from_row(r) -> dict[str, float]:
    par_pilier = {
        "VIGUEUR": ["entrainement", "seances", "pas", "sommeil", "charge_fraicheur"],
        "FORGE": ["engagement", "projets_fond"],
        "LOGOS": ["deep_focus", "projets_fond"],
        "RÉSONNANCE": ["ecran", "cloture"],
    }
    scores = {}
    for pilier, criteres in par_pilier.items():
        cle = "RESONNANCE" if pilier == "RÉSONNANCE" else pilier
        valeur = _moyenne_criteres(r, criteres)
        if valeur is not None and user_config.pilier_actif(cle):
            scores[pilier] = valeur
    return scores


def _palier(ok: bool, label: str, current, target: float, unit: str = "") -> str:
    val = current or 0
    mark = "✓" if ok else "✗"
    if ok:
        return f"{mark} {label} {val:.0f}{unit}"
    remaining = target - val
    return f"{mark} {label} {val:.0f}/{target:.0f}{unit} (reste {remaining:.0f}{unit})"


def _med(vals: list) -> float:
    s = sorted(v for v in vals if v is not None)
    if not s:
        return 0.0
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _reconcile_frozen_weeks() -> tuple[int, int]:
    """Réapplique is_frozen sur les semaines_audit couvertes par une pause, vécue ou en cours.

    Rattrape les semaines créées après coup (ex. rejouées / backfillées) ou
    dégelées à tort (ex. pause clôturée qui a effacé is_frozen sur des
    semaines déjà passées sous pause) qui ne sont pas encore marquées gelées.
    Comble aussi les semaines totalement absentes de semaines_audit (aucun
    log n'a eu lieu pendant la pause) pour qu'elles apparaissent dans
    l'historique au lieu de laisser un trou silencieux.
    Chaque pause n'est réappliquée que sur sa portion réellement vécue
    (date_debut → min(date_fin, aujourd'hui)) pour ne jamais geler par
    anticipation des semaines futures d'une pause déjà close prématurément.
    Retourne (semaines créées, semaines marquées gelées).
    """
    from src.core.system_engine import get_or_create_week_id

    today = today_local().isoformat()
    with db_session() as conn:
        freezes = conn.execute("SELECT date_debut, date_fin FROM system_freezes").fetchall()
        before = conn.execute("SELECT COUNT(*) FROM semaines_audit").fetchone()[0]

    for f in freezes:
        real_end = min(f["date_fin"], today)
        cursor_date = datetime.date.fromisoformat(f["date_debut"])
        end_date = datetime.date.fromisoformat(real_end)
        while cursor_date <= end_date:
            get_or_create_week_id(cursor_date.isoformat())
            cursor_date += datetime.timedelta(days=7)

    updated = 0
    with db_session() as conn:
        created = conn.execute("SELECT COUNT(*) FROM semaines_audit").fetchone()[0] - before
        for f in freezes:
            real_end = min(f["date_fin"], today)
            cur = conn.execute(
                "UPDATE semaines_audit SET is_frozen = 1"
                " WHERE week_start <= ? AND date(week_start, '+6 days') >= ? AND is_frozen = 0",
                (real_end, f["date_debut"]),
            )
            updated += cur.rowcount
    return created, updated


def _get_median_pentagon(before_week_start: str) -> dict[str, float] | None:
    """Médiane des 4 dernières semaines *complètes*, donc strictement avant la semaine courante."""
    with db_session() as conn:
        rows = conn.execute(
            _PILIER_QUERY
            + "WHERE week_start < ?"
            + " AND id NOT IN (SELECT id FROM semaines_audit WHERE is_frozen = 1)"
            + " ORDER BY week_start DESC LIMIT ?",
            (before_week_start, _N_WEEKS_MEDIAN),
        ).fetchall()

    if len(rows) < _N_WEEKS_MEDIAN:
        return None

    keys = list(_scores_from_row(rows[0]))
    per_pilier = {k: [] for k in keys}
    for r in rows:
        for k, v in _scores_from_row(r).items():
            per_pilier[k].append(v)

    return {k: round(_med(per_pilier[k]), 1) for k in keys}


def _pentagon_scores_from_db(week_start: str) -> dict[str, float]:
    with db_session() as conn:
        row = conn.execute(_PILIER_QUERY + "WHERE week_start = ?", (week_start,)).fetchone()
    if not row:
        return dict.fromkeys(("FORGE", "LOGOS", "VIGUEUR", "RÉSONNANCE"), 0.0)
    return _scores_from_row(row)


# ── Red Flags ─────────────────────────────────────────────────────────────────


def _detect_red_flags() -> list[tuple[str, str]]:
    flags: list[tuple[str, str]] = []
    with db_session() as conn:
        weeks_no_habits = conn.execute("""
            SELECT sa.week_start FROM semaines_audit sa
            LEFT JOIN habitude_logs hl ON hl.semaine_id = sa.id
            WHERE hl.id IS NULL AND sa.is_frozen = 0
            ORDER BY sa.week_start DESC LIMIT 2
        """).fetchall()
        if len(weeks_no_habits) >= 2:
            flags.append(("error", "2 semaines consécutives sans log d'habitudes."))
        last_sport = conn.execute(
            "SELECT sessions_sport FROM semaines_audit"
            " WHERE sessions_sport IS NOT NULL AND is_frozen = 0"
            " ORDER BY week_start DESC LIMIT 1"
        ).fetchone()
        if last_sport and last_sport["sessions_sport"] == 0:
            flags.append(("warning", "Aucune session de sport la semaine passée."))
        low_score = conn.execute(
            "SELECT week_start, score_semaine FROM semaines_audit"
            " WHERE score_semaine IS NOT NULL AND is_frozen = 0"
            " ORDER BY week_start DESC LIMIT 2"
        ).fetchall()
        if len(low_score) >= 2 and all(r["score_semaine"] < 33 for r in low_score):
            flags.append(("error", "2 semaines consécutives sous 33/100 — revoir les priorités."))
    return flags


# ── Analyse hebdomadaire ──────────────────────────────────────────────────────

_DAY_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


_METRIC_DEFS: dict[str, tuple[str, str]] = {
    "HRV (ms)": ("hrv", "vigueur"),
    "Sommeil (min)": ("sleep_min", "vigueur"),
    "CTL": ("ctl", "vigueur"),
    "Entraînement (min)": ("moving_time_min", "vigueur"),
    "Pas": ("steps", "vigueur"),
    "Focus (min)": ("focus_min", "focus"),
    "Écran distraction (min)": ("screen_min", "screen"),
}
_DEFAULT_METRICS = [
    "HRV (ms)",
    "Entraînement (min)",
    "Focus (min)",
    "CTL",
    "Écran distraction (min)",
]
_LINE_COLORS = [
    PALETTE["sky_blue"],
    PALETTE["amber"],
    PALETTE["blue_green"],
    "#e07b7b",
    "#9b8fe0",
    "#7bc4e0",
    "#e0c47b",
    "#a8e07b",
]


def _render_weekly_analysis() -> None:
    with db_session() as conn:
        weeks = conn.execute("""
            SELECT sa.id, sa.week_label, sa.week_start
            FROM semaines_audit sa
            ORDER BY sa.week_start DESC LIMIT 52
        """).fetchall()

    if not weeks:
        st.caption("Aucune semaine disponible.")
        return

    week_map = {w["id"]: dict(w) for w in weeks}
    selected_id = st.selectbox(
        "Semaine",
        options=[w["id"] for w in weeks],
        format_func=lambda x: week_map[x]["week_label"],
        key="analyse_week_sel",
    )

    week_start_str = week_map[selected_id]["week_start"]
    week_start = datetime.date.fromisoformat(week_start_str)
    week_end_str = (week_start + datetime.timedelta(days=7)).isoformat()
    day_isos = [(week_start + datetime.timedelta(days=i)).isoformat() for i in range(7)]
    is_current_week = week_start <= today_local() < week_start + datetime.timedelta(days=7)

    selected_metrics = st.multiselect(
        "Métriques",
        options=list(_METRIC_DEFS.keys()),
        default=_DEFAULT_METRICS,
        key="analyse_metrics_sel",
    )

    with db_session() as conn:
        habit_rows = conn.execute(
            "SELECT date_log, lecture_10min, jeune_intermittent FROM habitude_logs WHERE semaine_id = ?",
            (selected_id,),
        ).fetchall()
        vig_rows = conn.execute(
            "SELECT date_entry, hrv, sleep_min, ctl, moving_time_min, steps FROM vigueur_entries"
            " WHERE date_entry >= ? AND date_entry < ?",
            (week_start_str, week_end_str),
        ).fetchall()
        foc_rows = conn.execute(
            "SELECT date_session, SUM(duree_min) AS focus_min FROM focus_sessions"
            " WHERE date_session >= ? AND date_session < ? GROUP BY date_session",
            (week_start_str, week_end_str),
        ).fetchall()
        screen_rows = conn.execute(
            "SELECT substr(session_start, 1, 10) AS date,"
            " SUM(duration_seconds) / 60.0 AS screen_min"
            " FROM screen_sessions"
            " WHERE substr(session_start, 1, 10) >= ? AND substr(session_start, 1, 10) < ?"
            " AND package IN (SELECT package FROM apps_distrayantes)"
            " GROUP BY substr(session_start, 1, 10)",
            (week_start_str, week_end_str),
        ).fetchall()
        score_row = conn.execute(
            "SELECT * FROM v_score_semaine WHERE id = ?", (selected_id,)
        ).fetchone()
        today_prog_row = conn.execute(
            "SELECT * FROM v_progression_quotidienne WHERE date_log = ?",
            (today_local().isoformat(),),
        ).fetchone()

    by_date: dict[str, dict] = {d: {} for d in day_isos}
    for r in habit_rows:
        by_date.setdefault(r["date_log"], {}).update(dict(r))
    for r in vig_rows:
        by_date.setdefault(r["date_entry"], {}).update(dict(r))
    for r in foc_rows:
        by_date.setdefault(r["date_session"], {}).update({"focus_min": r["focus_min"]})
    for r in screen_rows:
        by_date.setdefault(r["date"], {}).update({"screen_min": r["screen_min"]})

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        for idx, metric_label in enumerate(selected_metrics):
            col_key, _ = _METRIC_DEFS[metric_label]
            y_vals = [by_date.get(d, {}).get(col_key) for d in day_isos]
            fig.add_trace(
                go.Scatter(
                    name=metric_label,
                    x=_DAY_FR,
                    y=y_vals,
                    mode="lines+markers",
                    line=dict(color=_LINE_COLORS[idx % len(_LINE_COLORS)], width=2),
                    marker=dict(size=5),
                    connectgaps=True,
                )
            )
        fig.update_layout(
            **{**_theme.plotly_layout(), "margin": dict(l=20, r=20, t=50, b=10)},
            font_size=12,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=11),
            ),
            height=260,
            xaxis=_theme.axis_style(show_grid=False),
            yaxis=_theme.axis_style(show_grid=True),
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.caption("Plotly requis.")

    # ── Paliers du jour, vers le rang S (semaine courante uniquement) ─────────
    # Modèle v2 (2026-08-31) : lu directement depuis v_progression_quotidienne au lieu de
    # dupliquer la logique en Python — garantit la cohérence avec la sidebar (components.py).
    if is_current_week:
        if today_prog_row:
            tp = dict(today_prog_row)
            mode_cfg = user_config.modes().get(tp["mode_actif"] or "")
            focus_target = (
                mode_cfg.focus_jour_min
                if mode_cfg
                else user_config.load()["seuils"]["jour"]["focus_defaut_min"]
            )
            seuils_j = user_config.load()["seuils"]["jour"]
            day_parts = [
                _palier(
                    bool(tp["ok_sport"]),
                    "Sport",
                    tp["moving_time_min"],
                    seuils_j["sport_min"],
                    "min",
                ),
                _palier(
                    bool(tp["ok_sommeil"]),
                    "Sommeil",
                    tp["sleep_min"],
                    seuils_j["sommeil_min"],
                    "min",
                ),
                _palier(bool(tp["ok_pas"]), "Pas", tp["steps"], seuils_j["pas"]),
                _palier(bool(tp["ok_focus"]), "Focus", tp["focus_min"], focus_target, "min"),
                _palier(
                    bool(tp["ok_focus_strat"]),
                    "Focus strat.",
                    tp["focus_strat_min"],
                    seuils_j["focus_strat_min"],
                    "min",
                ),
            ]
            screen_val = tp["screen_min"] or 0
            if tp["ok_ecran"]:
                day_parts.append(f"✓ Écran {screen_val:.0f}min")
            else:
                day_parts.append(f"✗ Écran {screen_val:.0f}min (seuil 30min ou baisse vs J-7)")

            st.caption(f"Aujourd'hui ({tp['rank']}, {tp['score_6']}/6) — " + " · ".join(day_parts))
        else:
            st.caption("Aujourd'hui — aucune donnée loguée.")

    # ── Paliers de la semaine, vers 100/100 (modèle v2, cf. §8 PLAN_AUDIT_HEBDO_V2.md) ──
    if score_row:
        sr = dict(score_row)

        seuils_w = user_config.load()["seuils"]["semaine"]
        week_parts = [
            _palier(
                bool(sr["ok_entrainement"]),
                "Entraîn.",
                sr["entrainement_min"],
                seuils_w["entrainement_min"],
                "min",
            ),
            _palier(bool(sr["ok_seances"]), "Séances", sr["seances"], seuils_w["seances"]),
            _palier(bool(sr["ok_pas"]), "Pas", sr["pas_total"], seuils_w["pas"]),
            _palier(
                bool(sr["ok_sommeil"]),
                "Sommeil moy./nuit",
                sr["sleep_moy"],
                seuils_w["sommeil_min"],
                "min",
            ),
        ]

        if sr["ok_charge_fraicheur"]:
            week_parts.append(
                f"✓ Charge/Fraîch. TSB {sr['tsb']:+.1f}"
                if sr["tsb"] is not None
                else "✓ Charge/Fraîch."
            )
        else:
            deload_txt = " (décharge)" if sr["is_deload_week"] else ""
            tsb_txt = f"{sr['tsb']:+.1f}" if sr["tsb"] is not None else "—"
            week_parts.append(f"✗ Charge/Fraîch. TSB {tsb_txt}{deload_txt}")

        screen = sr["screen_distraction_min"] or 0
        screen_prev = sr["screen_distraction_min_prev"]
        if sr["ok_ecran"]:
            week_parts.append(f"✓ Écran dist. {screen:.0f}min")
        else:
            cible = (
                f"seuil {seuils_w['ecran_max_min']:.0f}min ou < {screen_prev:.0f}min S préc."
                if screen_prev is not None
                else f"seuil {seuils_w['ecran_max_min']:.0f}min"
            )
            week_parts.append(f"✗ Écran dist. {screen:.0f}min ({cible})")

        mode_cfg = user_config.modes().get(sr["mode_actif"] or "")
        focus_target = (
            mode_cfg.focus_semaine_min
            if mode_cfg
            else user_config.load()["seuils"]["semaine"]["focus_defaut_min"] + 1
        )
        week_parts.append(
            _palier(bool(sr["ok_deep_focus"]), "Focus", sr["deep_focus_min"], focus_target, "min")
        )
        week_parts.append(
            _palier(
                bool(sr["ok_projets_fond"]),
                "Projets fond",
                sr["focus_projets_fond_min"],
                seuils_w["projets_fond_min"],
                "min",
            )
        )

        if user_config.engagement_actif():
            libelle = user_config.engagement_libelle()
            if sr["ok_engagement"]:
                week_parts.append(f"✓ {libelle}")
            else:
                week_parts.append(
                    f"✗ {libelle} {sr['focus_engagement_min']:.0f}min · "
                    f"{sr['jours_engagement_semaine']:.0f}j "
                    f"(besoin ≥{seuils_w['engagement_min']:.0f}min "
                    f"ou ≥{seuils_w['engagement_jours']:.0f}j)"
                )

        if sr["ok_cloture"]:
            week_parts.append("✓ Clôture")
        else:
            week_parts.append(f"✗ Clôture ({sr['social'] or 'non renseigné'})")

        st.caption(f"Score semaine : {sr['score_semaine']:.0f}/100 — " + " · ".join(week_parts))


# ── Historique ────────────────────────────────────────────────────────────────


def _render_history() -> None:
    with db_session() as conn:
        rows = conn.execute("""
            SELECT week_start, week_label, mode_actif, is_frozen, score_semaine
            FROM semaines_audit
            ORDER BY week_start DESC LIMIT 13
        """).fetchall()
        freezes = conn.execute("SELECT date_debut, date_fin, raison FROM system_freezes").fetchall()
    if not rows:
        return
    try:
        import pandas as pd

        records = [dict(r) for r in rows]
        for r in records:
            week_start = r.pop("week_start")
            # Colonne texte homogène : mélanger nombres et « freeze » casse la conversion Arrow
            score = r["score_semaine"]
            r["score_semaine"] = None if score is None else f"{score:g}"
            if r.pop("is_frozen"):
                week_end = (
                    datetime.date.fromisoformat(week_start) + datetime.timedelta(days=6)
                ).isoformat()
                raison = next(
                    (
                        f["raison"]
                        for f in freezes
                        if week_start <= f["date_fin"] and week_end >= f["date_debut"]
                    ),
                    None,
                )
                r["mode_actif"] = f"Pause ({raison[:40]})" if raison else "Pause"
                r["score_semaine"] = "freeze"

        df = pd.DataFrame(records).rename(
            columns={
                "week_label": "Semaine",
                "mode_actif": "Mode",
                "score_semaine": "Score",
            }
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception:
        for r in rows:
            score = "freeze" if r["is_frozen"] else r["score_semaine"]
            st.text(f"{r['week_label']} | {r['mode_actif']} | S:{score}")


# ── Calendrier / Emploi du temps ──────────────────────────────────────────────


def _ensure_taches_cols() -> None:
    with db_session() as conn:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(taches)").fetchall()}
        for col, defn in [
            ("description", "TEXT"),
            ("heure_debut", "TEXT"),
            ("heure_fin", "TEXT"),
            ("date_debut", "TEXT"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE taches ADD COLUMN {col} {defn}")


_PRIO_META: dict[int, tuple[str, str, str, str]] = {
    1: ("P1", PALETTE["amber"], "#023047", "Critique"),
    2: ("P2", "#e67e22", "#ffffff", "Nice to have"),
    3: ("P3", PALETTE["sky_blue"], "#023047", "Peut déplacer"),
}

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _render_weekly_tasks(today: datetime.date) -> None:
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    with db_session() as conn:
        rows = conn.execute("""
            SELECT t.id, t.titre, t.description, t.priorite,
                   t.date_debut, t.date_echeance, t.heure_debut, t.heure_fin,
                   o.titre AS obj_titre, o.pilier
            FROM taches t
            LEFT JOIN objectifs o ON t.objectif_id = o.id
            WHERE t.statut NOT IN ('fait', 'annule')
            ORDER BY t.priorite ASC,
                     CASE WHEN t.date_echeance IS NULL THEN 1 ELSE 0 END ASC,
                     t.date_echeance ASC
        """).fetchall()

    if not rows:
        st.caption("Aucune tâche active.")
        return

    overdue = [
        r for r in rows if r["date_echeance"] and r["date_echeance"][:10] < today.isoformat()
    ]
    this_week = [
        r
        for r in rows
        if r["date_echeance"]
        and today.isoformat() <= r["date_echeance"][:10] <= week_end.isoformat()
    ]
    later = [
        r for r in rows if not r["date_echeance"] or r["date_echeance"][:10] > week_end.isoformat()
    ]

    def _badge(text: str, bg: str, fg: str, size: str = ".7rem") -> str:
        return (
            f"<span style='background:{bg};color:{fg};padding:2px 8px;"
            f"border-radius:3px;font-size:{size};font-weight:600;white-space:nowrap'>{text}</span>"
        )

    def _row_section(task_list: list) -> None:
        for t in task_list:
            c_prio, c_urg, c_title, c_obj, c_fait, c_del = st.columns(
                [0.45, 0.8, 3.5, 2, 0.75, 0.42], vertical_alignment="center"
            )
            label, bg, fg, _ = _PRIO_META.get(t["priorite"], ("P?", GRAY, "#fff", ""))

            with c_prio:
                st.markdown(_badge(label, bg, fg), unsafe_allow_html=True)

            with c_urg:
                if t["date_echeance"]:
                    delta = (datetime.date.fromisoformat(t["date_echeance"][:10]) - today).days
                    if delta < 0:
                        txt, col = f"{abs(delta)}j retard", "#e74c3c"
                    elif delta == 0:
                        txt, col = "Aujourd'hui", PALETTE["amber"]
                    elif delta <= 2:
                        txt, col = f"+{delta}j", "#e67e22"
                    else:
                        txt, col = f"+{delta}j", PALETTE["sky_blue"]
                else:
                    txt, col = "—", GRAY
                st.markdown(
                    f"<span style='color:{col};font-size:.74rem;white-space:nowrap'>{txt}</span>",
                    unsafe_allow_html=True,
                )

            with c_title:
                time_str = ""
                if t["heure_debut"]:
                    time_str = f"  ·  {t['heure_debut']}"
                    if t["heure_fin"]:
                        time_str += f"–{t['heure_fin']}"
                st.markdown(f"**{t['titre']}**{time_str}")
                if t["description"]:
                    st.caption(t["description"][:120])

            with c_obj:
                if t["obj_titre"]:
                    st.caption(f"{t['pilier']} — {t['obj_titre']}")

            with c_fait:
                if st.button("Fait", key=f"fait_{t['id']}", use_container_width=True):
                    with db_session() as conn:
                        conn.execute(
                            "UPDATE taches SET statut='fait', completed_at=datetime('now') WHERE id=?",
                            (t["id"],),
                        )
                    st.rerun()

            with c_del:
                if st.button("×", key=f"del_{t['id']}", use_container_width=True):
                    with db_session() as conn:
                        conn.execute("DELETE FROM taches WHERE id=?", (t["id"],))
                    st.rerun()

    def section_header(txt: str, col: str) -> None:
        st.markdown(
            f"<p style='color:{col};font-size:.78rem;letter-spacing:.07em;"
            f"font-weight:600;margin-bottom:4px'>{txt}</p>",
            unsafe_allow_html=True,
        )

    if overdue:
        section_header("EN RETARD", "#e74c3c")
        _row_section(overdue)

    if this_week:
        if overdue:
            st.divider()
        iso = today.isocalendar()
        wlabel = f"S.{iso.week} — {week_start.strftime('%-d %b')} – {week_end.strftime('%-d %b')}"
        section_header(f"SEMAINE {wlabel}", PALETTE["sky_blue"])
        _row_section(this_week)

    if later:
        if overdue or this_week:
            st.divider()
        section_header("PLUS TARD", GRAY)
        _row_section(later)


def _render_calendar_tab() -> None:
    today = today_local()
    _ensure_taches_cols()

    with db_session() as conn:
        objectifs_rows = conn.execute(
            "SELECT id, titre, pilier FROM objectifs WHERE statut = 'actif' ORDER BY pilier, titre"
        ).fetchall()

    col_cal, col_side = st.columns([2.2, 1], gap="medium")

    with col_cal:
        cal_src = get_secret("calendar", "src")
        if cal_src:
            components.iframe(
                "https://calendar.google.com/calendar/embed"
                f"?src={quote(cal_src, safe='')}&ctz={quote(tz().key, safe='')}",
                height=600,
                scrolling=False,
            )
        else:
            st.info("Calendrier non configuré — définir CALENDAR_SRC dans secrets.env.")

    with col_side:
        with st.expander("+ Ajouter une tâche", expanded=True):
            with st.form("cal_add_task"):
                titre = st.text_input("Titre")
                desc_val = st.text_area(
                    "Description", height=68, placeholder="Protocole, détail de la séance..."
                )
                c1, c2 = st.columns(2)
                with c1:
                    date_debut_val = st.date_input("Début", today, key="cal_task_deb")
                with c2:
                    date_fin_val = st.date_input(
                        "Fin / Échéance",
                        today + datetime.timedelta(days=1),
                        key="cal_task_fin",
                    )
                c3, c4 = st.columns(2)
                with c3:
                    heure_deb_raw = st.text_input(
                        "Heure début", placeholder="09:00", key="cal_h_deb"
                    )
                with c4:
                    heure_fin_raw = st.text_input("Heure fin", placeholder="10:30", key="cal_h_fin")
                priorite = st.select_slider(
                    "Priorité",
                    options=[1, 2, 3],
                    value=3,
                    format_func=lambda x: {
                        1: "P1 — Critique",
                        2: "P2 — Nice to have",
                        3: "P3 — Peut déplacer",
                    }[x],
                    key="cal_prio",
                )
                obj_options: dict[str, int | None] = {"— Sans objectif": None}
                obj_options.update(
                    {f"{o['pilier']} — {o['titre']}": o["id"] for o in objectifs_rows}
                )
                obj_sel = st.selectbox("Objectif lié", list(obj_options.keys()))
                if st.form_submit_button("Créer", use_container_width=True):
                    if titre.strip():
                        hd = (
                            heure_deb_raw.strip() if _TIME_RE.match(heure_deb_raw.strip()) else None
                        )
                        hf = (
                            heure_fin_raw.strip() if _TIME_RE.match(heure_fin_raw.strip()) else None
                        )
                        with db_session() as conn:
                            conn.execute(
                                "INSERT INTO taches"
                                " (titre, description, objectif_id, priorite, statut,"
                                "  date_debut, date_echeance, heure_debut, heure_fin)"
                                " VALUES (?, ?, ?, ?, 'todo', ?, ?, ?, ?)",
                                (
                                    titre.strip(),
                                    desc_val.strip() or None,
                                    obj_options[obj_sel],
                                    priorite,
                                    date_debut_val.isoformat(),
                                    date_fin_val.isoformat(),
                                    hd,
                                    hf,
                                ),
                            )
                        st.rerun()
                    else:
                        st.error("Titre requis.")

    st.markdown(
        "<h4 style='font-weight:600;letter-spacing:.05em;color:var(--text-color);"
        "margin-top:2rem;margin-bottom:.5rem'>TÂCHES ACTIVES</h4>",
        unsafe_allow_html=True,
    )
    _render_weekly_tasks(today)


# ── Rendu principal ───────────────────────────────────────────────────────────


def render(current_week: dict | None) -> None:
    st.header("JOURNAL DE BORD")

    if not current_week:
        st.markdown("---")
        st.warning("Aucune semaine d'audit active. Enregistrez un log pour initialiser.")
        return

    # ── Mode + semaine ────────────────────────────────────────────────────────
    mode = current_week.get("mode_actif") or user_config.default_mode()
    mode_color = MODE_COLORS.get(mode, PALETTE["blue_green"])
    st.markdown("---")
    col_b, col_l = st.columns([1, 6])
    with col_b:
        st.markdown(
            f'<span style="background:{mode_color};color:white;padding:4px 14px;'
            f'border-radius:20px;font-size:.85rem;font-weight:600;">MODE {user_config.mode_label(mode)}</span>',
            unsafe_allow_html=True,
        )
    with col_l:
        st.markdown(f"**{current_week['week_label']}**")

    # ── Pentagone ─────────────────────────────────────────────────────────────
    median_scores = _get_median_pentagon(current_week["week_start"])
    if median_scores:
        scores = median_scores
        pentagon_label = f"Médiane — {_N_WEEKS_MEDIAN} dernières semaines"
    else:
        scores = _pentagon_scores_from_db(current_week["week_start"])
        pentagon_label = "Semaine courante"

    energy = round(sum(scores.values()) / len(scores), 1) if scores else 0.0

    col_radar, col_right = st.columns([1.4, 1], gap="large")

    with col_radar:
        col_cap, col_refresh = st.columns([3, 2])
        with col_cap:
            st.caption(pentagon_label)
        with col_refresh:
            if st.button(
                "Recalculer",
                key="refresh_median_pentagon",
                icon=":material/refresh:",
                use_container_width=True,
                help=(
                    "Vérifie que les semaines gelées sont à jour, "
                    "puis recalcule le score médian des 4 dernières semaines"
                ),
            ):
                created, updated = _reconcile_frozen_weeks()
                if created or updated:
                    parts = []
                    if created:
                        parts.append(f"{created} semaine(s) créée(s)")
                    if updated:
                        parts.append(f"{updated} semaine(s) resynchronisée(s) comme gelée(s)")
                    st.toast(" · ".join(parts) + ".")
                st.rerun()
        try:
            import plotly.graph_objects as go

            axes = list(scores.keys()) + [list(scores.keys())[0]]
            vals = list(scores.values()) + [list(scores.values())[0]]
            fig = go.Figure()
            fig.add_trace(
                go.Scatterpolar(
                    r=[100] * len(axes),
                    theta=axes,
                    fill="toself",
                    fillcolor=CHART_COLORS["target_fill"],
                    line=dict(color=CHART_COLORS["target_line"], width=1, dash="dot"),
                    hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatterpolar(
                    r=vals,
                    theta=axes,
                    fill="toself",
                    fillcolor=CHART_COLORS["score_fill"],
                    line=dict(color=CHART_COLORS["score_line"], width=2.5),
                    hovertemplate="%{theta} : %{r:.0f}%<extra></extra>",
                )
            )
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 100], showticklabels=False),
                    angularaxis=dict(
                        tickfont=dict(size=12, color=_theme.text()),
                        rotation=45,
                        direction="clockwise",
                    ),
                    bgcolor=TRANSPARENT,
                ),
                **{**_theme.plotly_layout(), "margin": dict(l=60, r=60, t=40, b=40)},
                font_size=12,
                showlegend=False,
                height=310,
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.info("Plotly requis pour le radar.")

    with col_right:
        label = "Score médian" if median_scores else "Énergie Système"
        st.markdown(f"**{label}**")
        st.metric(
            "Score global",
            f"{energy:.0f} / 100",
            help=(
                "Moyenne des piliers actifs sur les 4 dernières semaines complètes.\n\n"
                "Chaque pilier = % de critères binaires validés. Seuils, poids et critères "
                "actifs : `config/user.toml`.\n"
                "- VIGUEUR : entraînement, séances, pas, sommeil, charge/fraîcheur (TSB)\n"
                f"- FORGE : {user_config.engagement_libelle().lower()} (si activé), projets de fond\n"
                "- LOGOS : deep focus selon le mode, projets de fond\n"
                "- RÉSONNANCE : écran distraction, clôture de l'audit"
            ),
        )
        st.progress(int(energy))
        st.markdown("---")
        for pilier, score in scores.items():
            st.markdown(f"**{pilier}** — {score:.0f}%")

    # ── Analyse ───────────────────────────────────────────────────────────────
    st.markdown("---")

    tab_analyse, tab_histo, tab_cal = st.tabs(
        ["Analyse semaine", "Historique 13S", "Emploi du temps"]
    )
    with tab_analyse:
        _render_weekly_analysis()
    with tab_histo:
        _render_history()
    with tab_cal:
        _render_calendar_tab()
