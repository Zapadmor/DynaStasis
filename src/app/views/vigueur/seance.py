"""Séance en cours : saisie des séries, fin de séance."""

from __future__ import annotations

import streamlit as st

from src.app.views.vigueur.chronometre import _render_emom_timer
from src.collectors.workout_db import (
    compute_load,
    finish_session,
    get_exercises,
    save_session_exercises,
)
from src.services import vigueur, workouts


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

            workouts.renumber_sets(ex["sets"])

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
        workouts.reposition(exercises)
        st.rerun()
    if move_down is not None:
        exercises[move_down], exercises[move_down + 1] = (
            exercises[move_down + 1],
            exercises[move_down],
        )
        workouts.reposition(exercises)
        st.rerun()
    if to_delete_ex is not None:
        exercises.pop(to_delete_ex)
        workouts.reposition(exercises)
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
        workouts.renumber_sets(sets_list)
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

    row = vigueur.resume_seance(session_id)

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
