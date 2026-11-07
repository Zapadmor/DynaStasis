"""Historique des séances : modification, suppression, rattachement Intervals.icu."""

from __future__ import annotations

import datetime
from collections.abc import Callable

import streamlit as st

from src.collectors.workout_db import sync_intervals_workout_links


def _duree(s: dict) -> str:
    if s.get("duration_min"):
        return f" · {s['duration_min']:g} min"
    if s.get("started_at") and s.get("finished_at"):
        try:
            start = datetime.datetime.fromisoformat(s["started_at"])
            end = datetime.datetime.fromisoformat(s["finished_at"])
            return f" · {int((end - start).total_seconds() / 60)} min"
        except ValueError:
            pass
    return ""


def _render_history(
    sessions: list[dict],
    on_edit: Callable[[int], None],
    confirm_delete_key: str,
) -> None:
    show_key = "workout_show_history"
    if show_key not in st.session_state:
        st.session_state[show_key] = False

    is_open = st.session_state[show_key]
    hdr_col, sync_col = st.columns([5, 2])
    with hdr_col:
        if st.button(
            f"HISTORIQUE  ({len(sessions)})  {'▾' if is_open else '▸'}", key="workout_hist_toggle"
        ):
            st.session_state[show_key] = not is_open
            st.rerun()
    with sync_col:
        if st.button("Sync Intervals (30 j)", key="workout_sync_intervals"):
            try:
                from src.collectors.intervals_client import IntervalsClient

                activities = IntervalsClient().get_activities(lookback_days=30)
                n_linked = sync_intervals_workout_links(activities)
                if n_linked:
                    st.success(f"{n_linked} séance(s) liée(s) à Intervals.")
                else:
                    st.info("Aucune nouvelle liaison trouvée.")
            except Exception as exc:
                st.error(f"Erreur Intervals.icu : {exc}")

    if not st.session_state[show_key]:
        return

    for s in sessions:
        volume = f" · {s['session_volume_kg']:.0f} kg" if s.get("session_volume_kg") else ""
        badge = " · Intervals" if s.get("intervals_activity_id") else ""
        info_col, btn_edit, btn_del = st.columns([6, 1, 1])
        with info_col:
            st.markdown(
                f"**{s['date_entry']}** — {s['name']}"
                f" · {s['nb_exercises']} exos"
                f" · {s['nb_completed']}/{s['nb_sets']} séries{_duree(s)}{volume}{badge}"
            )
        with btn_edit:
            st.button(
                "Mod",
                key=f"hist_edit_{s['id']}",
                help="Modifier",
                on_click=on_edit,
                args=(s["id"],),
            )
        with btn_del:
            if st.button("Del", key=f"hist_del_{s['id']}", help="Supprimer"):
                st.session_state[confirm_delete_key] = s["id"]
                st.rerun()
