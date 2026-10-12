"""Onglet « Objectifs » : objectifs, tâches, accès SQLite."""

from __future__ import annotations

import streamlit as st

from src.app.components import PALETTE
from src.app.theme import contrast_text as _contrast_text
from src.services import objectifs as objectifs_service

# ── Objectifs ─────────────────────────────────────────────────────────────────

_PILIER_COLORS = {
    "FORGE": PALETTE["amber"],
    "LOGOS": PALETTE["blue_green"],
    "VIGUEUR": PALETTE["tiger"],
    "RESONNANCE": PALETTE["sky_blue"],
    "SYSTEME": "#666666",
}

_PRIORITE_LABELS = {1: "Haute", 2: "Normale", 3: "Basse"}
_PRIORITE_COLORS = {1: PALETTE["tiger"], 2: PALETTE["amber"], 3: PALETTE["sky_blue"]}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS OBJECTIFS — CRUD SQLite
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# ONGLET OBJECTIFS
# ─────────────────────────────────────────────────────────────────────────────


def _tab_objectifs() -> None:
    st.markdown("### Objectifs & Tâches")

    # ── Bouton de synchronisation ─────────────────────────────────────────────
    col_sync, col_info = st.columns([1, 5])
    with col_sync:
        if st.button("Synchroniser", use_container_width=True, key="sync_objectifs"):
            from src.database.connection import init_db

            init_db()
            st.rerun()
    with col_info:
        st.caption("Charge / migre les objectifs depuis la base SQLite locale.")

    st.markdown("")

    # ── Formulaire nouvel objectif ────────────────────────────────────────────
    with st.expander("+ Nouvel objectif", expanded=False):
        with st.form("form_new_obj", clear_on_submit=True):
            col_t, col_p = st.columns([3, 1])
            with col_t:
                obj_titre = st.text_input("Titre *")
            with col_p:
                obj_pilier = st.selectbox(
                    "Pilier", ["FORGE", "LOGOS", "VIGUEUR", "RESONNANCE", "SYSTEME"]
                )
            col_d, col_pr = st.columns(2)
            with col_d:
                obj_date = st.text_input("Date cible (AAAA-MM-JJ)", placeholder="optionnel")
            with col_pr:
                obj_priorite = st.selectbox(
                    "Priorité", [1, 2, 3], format_func=lambda x: _PRIORITE_LABELS[x]
                )
            obj_desc = st.text_area("Description", height=60)
            if st.form_submit_button("Créer l'objectif") and obj_titre.strip():
                objectifs_service.creer_objectif(
                    obj_titre.strip(),
                    obj_pilier,
                    obj_date.strip() or None,
                    obj_desc,
                    obj_priorite,
                )
                st.rerun()

    st.markdown("")

    objectifs, err = objectifs_service.charger_objectifs()
    if err:
        st.error(f"Erreur DB : {err}")
        st.caption("Cliquez sur 🔄 Synchroniser pour appliquer les migrations manquantes.")
        return
    if not objectifs:
        st.info("Aucun objectif actif. Créez-en un ci-dessus.")
        return

    for obj in objectifs:
        taches = objectifs_service.charger_taches(obj["id"])
        done_count = sum(1 for t in taches if t["statut"] == "fait")
        total_count = len(taches)
        pct = done_count / total_count if total_count > 0 else 0.0
        pilier_color = _PILIER_COLORS.get(obj["pilier"], "#666666")

        # ── En-tête objectif ──────────────────────────────────────────────────
        col_head, col_del = st.columns([11, 1])
        with col_head:
            echeance_str = (
                f' · <span style="opacity:.6;font-size:.8rem;">{obj["date_cible"]}</span>'
                if obj.get("date_cible")
                else ""
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
                f'<span style="font-weight:700;font-size:1rem;">{obj["titre"]}</span>'
                f'<span style="background:{pilier_color};color:{_contrast_text(pilier_color)};padding:2px 10px;'
                f'border-radius:12px;font-size:.72rem;font-weight:700;">{obj["pilier"]}</span>'
                f'<span style="background:var(--secondary-background-color);color:var(--text-color);padding:2px 10px;'
                f'border-radius:12px;font-size:.72rem;">{obj["statut"]}</span>'
                f"{echeance_str}"
                f"</div>",
                unsafe_allow_html=True,
            )
            if obj.get("description"):
                st.caption(obj["description"])
        with col_del:
            if st.button("✕", key=f"del_obj_{obj['id']}", help="Archiver cet objectif"):
                objectifs_service.archiver_objectif(obj["id"])
                st.rerun()

        # ── Barre de progression ──────────────────────────────────────────────
        progress_text = (
            f"{done_count} / {total_count} tâches · {pct * 100:.0f}%"
            if total_count > 0
            else "Aucune tâche"
        )
        st.progress(pct, text=progress_text)

        # ── Liste des tâches ──────────────────────────────────────────────────
        # Les tâches "fait" sont archivées automatiquement (statut conservé en DB)
        # et retirées de l'affichage dès qu'elles sont cochées.
        taches_visibles = [t for t in taches if t["statut"] != "fait"]
        for tache in taches_visibles:
            t_done = tache["statut"] == "fait"
            c_chk, c_lbl, c_del = st.columns([1, 11, 1])
            with c_chk:
                new_val = st.checkbox(
                    "", value=t_done, key=f"tache_{tache['id']}", label_visibility="collapsed"
                )
                if new_val != t_done:
                    objectifs_service.cocher_tache(tache["id"], new_val)
                    st.rerun()
            with c_lbl:
                prio_color = _PRIORITE_COLORS.get(tache["priorite"], "#666666")
                strike = "text-decoration:line-through;opacity:.45;" if t_done else ""
                echeance = (
                    f'<span style="opacity:.5;font-size:.78rem;"> · {tache["date_echeance"]}</span>'
                    if tache.get("date_echeance")
                    else ""
                )
                st.markdown(
                    f'<div style="{strike}font-size:.88rem;padding:4px 0;">'
                    f'<span style="color:{prio_color};margin-right:6px;">●</span>'
                    f"{tache['titre']}{echeance}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with c_del:
                if st.button("✕", key=f"del_tache_{tache['id']}", help="Supprimer la tâche"):
                    objectifs_service.supprimer_tache(tache["id"])
                    st.rerun()

        # ── Formulaire ajout tâche ────────────────────────────────────────────
        with st.expander(f"+ Tâche pour « {obj['titre']} »", expanded=False):
            with st.form(f"form_tache_{obj['id']}", clear_on_submit=True):
                c_tt, c_tp = st.columns([3, 1])
                with c_tt:
                    t_titre = st.text_input("Titre de la tâche *")
                with c_tp:
                    t_prio = st.selectbox(
                        "Priorité", [1, 2, 3], format_func=lambda x: _PRIORITE_LABELS[x]
                    )
                t_date = st.text_input("Échéance (AAAA-MM-JJ)", placeholder="optionnel")
                if st.form_submit_button("Ajouter") and t_titre.strip():
                    objectifs_service.creer_tache(
                        obj["id"], t_titre.strip(), t_prio, t_date.strip() or None
                    )
                    st.rerun()

        st.markdown("---")
