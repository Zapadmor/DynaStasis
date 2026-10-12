"""Onglet « Log Workouts » : accueil et nouvelle séance."""

from __future__ import annotations

import datetime

import streamlit as st

from src.app.views.vigueur.historique import _render_history
from src.app.views.vigueur.seance import _render_active_session
from src.collectors.workout_db import (
    create_session,
    delete_session,
    get_sessions,
    get_template_detail,
    get_templates,
    update_template_from_session,
)
from src.core.tz import today_local

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
