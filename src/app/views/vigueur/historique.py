"""Historique des séances."""

from __future__ import annotations

import datetime

import streamlit as st

from src.collectors.workout_db import (
    get_session_detail,
    sync_intervals_workout_links,
)


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
