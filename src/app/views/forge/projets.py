"""Onglet « Projets en cours »."""

from __future__ import annotations

import streamlit as st

from src.app.components import PALETTE
from src.app.theme import contrast_text as _contrast_text
from src.services import projets

# ─────────────────────────────────────────────────────────────────────────────
# ONGLET PROJETS EN COURS
# ─────────────────────────────────────────────────────────────────────────────


def _on_toggle_projet_tache(tache_id: int, key: str) -> None:
    projets.set_tache(tache_id, bool(st.session_state[key]))


def _badge(texte: str, color: str) -> None:
    st.markdown(
        f'<span style="background:{color};color:{_contrast_text(color)};padding:3px 12px;'
        f'border-radius:14px;font-size:.78rem;font-weight:700;">{texte}</span>',
        unsafe_allow_html=True,
    )


def _render_projet(p: dict) -> None:
    col_title, col_badge = st.columns([5, 1])
    with col_title:
        st.markdown(f"**{p['titre']}**")
        if p["description"]:
            st.caption(p["description"])
    with col_badge:
        _badge(f"{p['faites']}/{p['total']}", PALETTE["blue_green"])
    if p["total"]:
        st.progress(p["faites"] / p["total"])

    phase = p["phase"]
    if phase:
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"Phase courante : **{phase['titre']}**")
        with c2:
            _badge("EN COURS", PALETTE["amber"])
        if phase["objectif"]:
            st.caption(f"Objectif : {phase['objectif']}")
        for t in phase["taches"]:
            key = f"projet_tache_{t['id']}"
            st.checkbox(
                t["libelle"],
                value=bool(t["fait"]),
                key=key,
                on_change=_on_toggle_projet_tache,
                args=(t["id"], key),
            )
        if phase["prochaine_etape"]:
            st.info(f"Prochaine étape : {phase['prochaine_etape']}")
        for note_title, note_body in phase["notes"]:
            st.markdown(
                f'<div style="border-left:2px solid {PALETTE["amber"]};'
                f'padding:6px 14px;margin:8px 0;font-size:.85rem;">'
                f"<strong>{note_title}</strong><br>"
                f'<span style="white-space:pre-line;">{note_body}</span></div>',
                unsafe_allow_html=True,
            )
    elif p["total"]:
        st.success("Toutes les phases sont validées.")
        if st.button("Marquer le projet comme terminé", key=f"projet_done_{p['id']}"):
            projets.changer_statut(p["id"], "termine")
            st.rerun()
    else:
        st.caption("Aucune phase ni tâche définie — voir « Gérer les projets » ci-dessous.")

    if p["phases"]:
        with st.expander("Toutes les phases"):
            for ph in p["phases"]:
                if ph["total"] and ph["faites"] == ph["total"]:
                    mark = "✓"
                elif phase and ph["id"] == phase["id"]:
                    mark = "▸"
                else:
                    mark = "○"
                st.markdown(f"{mark} {ph['titre']} — {ph['faites']}/{ph['total']}")


def _projets_gestion() -> None:
    with st.expander("+ Gérer les projets"):
        with st.form("projet_nouveau", clear_on_submit=True):
            st.markdown("**Nouveau projet**")
            titre = st.text_input("Titre")
            description = st.text_input("Description (optionnel)")
            if st.form_submit_button("Créer le projet") and titre.strip():
                projets.creer_projet(titre.strip(), description.strip() or None)
                st.rerun()

        gerables = projets.projets_gerables()
        if not gerables:
            return

        with st.form("projet_phase", clear_on_submit=True):
            st.markdown("**Nouvelle phase** (ajoutée à la suite des phases existantes)")
            projet = st.selectbox("Projet", gerables, format_func=lambda x: x["titre"])
            titre_phase = st.text_input("Titre de la phase")
            objectif = st.text_input("Objectif (optionnel)")
            etape = st.text_input("Prochaine étape (optionnel)")
            if st.form_submit_button("Ajouter la phase") and titre_phase.strip():
                projets.ajouter_phase(
                    projet["id"],
                    titre_phase.strip(),
                    objectif.strip() or None,
                    etape.strip() or None,
                )
                st.rerun()

        phases = projets.phases_gerables()
        if phases:
            with st.form("projet_tache", clear_on_submit=True):
                st.markdown("**Nouvelle tâche**")
                phase = st.selectbox(
                    "Phase", phases, format_func=lambda x: f"{x['projet']} — {x['phase']}"
                )
                libelle = st.text_input("Libellé de la tâche")
                if st.form_submit_button("Ajouter la tâche") and libelle.strip():
                    projets.ajouter_tache(phase["id"], libelle.strip())
                    st.rerun()

        with st.form("projet_statut"):
            st.markdown("**Changer le statut d'un projet**")
            projet = st.selectbox(
                "Projet",
                gerables,
                format_func=lambda x: f"{x['titre']} ({x['statut']})",
                key="projet_statut_select",
            )
            statut = st.selectbox("Nouveau statut", projets.STATUTS)
            if st.form_submit_button("Appliquer"):
                projets.changer_statut(projet["id"], statut)
                st.rerun()


def _tab_projets() -> None:
    st.markdown("### Projets en cours")
    en_cours = projets.projets_en_cours()
    if not en_cours:
        st.info("Aucun projet en cours.")
    for p in en_cours:
        _render_projet(p)
        st.markdown("---")
    _projets_gestion()
