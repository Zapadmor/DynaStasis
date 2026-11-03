"""Sous-onglet « Chantiers & RETEX » des notes pour trop tard : introspection suivie dans le temps."""

from __future__ import annotations

import html

import streamlit as st

from src.app.components import GRAY, PALETTE
from src.core.tz import today_local
from src.services import npt

_STATUT_COLORS = {"Ouvert": PALETTE["sky_blue"], "En cours": PALETTE["amber"], "Clos": GRAY}
_TOUS = "Tous"
_MOI = "Moi (sans personne)"


def _render_chantiers() -> None:
    st.caption(
        "RETEX, chantiers psy, exercices, écueils, défis relationnels, qualités et défauts : "
        "à creuser dans le temps, avec une personne ou sur toi-même."
    )
    if not npt.chantiers_prets():
        st.info("Tables non initialisées. Lancez `python main.py init-db`.")
        return

    persons = npt.personnes()
    noms = {p["id"]: f"{p['prenom']} {p['nom']}".strip() for p in persons}
    chantiers = npt.chantiers()

    # ── Filtres ──────────────────────────────────────────────────────────────
    col_p, col_t, col_s = st.columns(3)
    with col_p:
        f_pers = st.selectbox("Personne", [_TOUS, _MOI, *noms.values()], key="npt_ch_f_pers")
    with col_t:
        f_type = st.selectbox("Type", [_TOUS, *npt.TYPES_CHANTIER], key="npt_ch_f_type")
    with col_s:
        f_statut = st.selectbox(
            "Statut", ["Non clos", _TOUS, *npt.STATUTS_CHANTIER], key="npt_ch_f_statut"
        )

    def _garde(c: dict) -> bool:
        if f_pers == _MOI and c["personne_id"] is not None:
            return False
        if f_pers not in (_TOUS, _MOI) and c["personne"] != f_pers:
            return False
        if f_type != _TOUS and c["type"] != f_type:
            return False
        if f_statut == "Non clos":
            return c["statut"] != "Clos"
        return f_statut == _TOUS or c["statut"] == f_statut

    visibles = [c for c in chantiers if _garde(c)]
    if not visibles:
        st.info("Aucun chantier pour ces filtres.")

    # ── Liste ────────────────────────────────────────────────────────────────
    for c in visibles:
        color = _STATUT_COLORS.get(c["statut"], GRAY)
        cible = c["personne"] or "Moi"
        titre = html.escape(c["titre"])
        with st.expander(f"{c['type']} · {c['titre']} — {cible} · {c['statut']}"):
            st.markdown(
                f'<div style="border-left:3px solid {color};padding:2px 12px;">'
                f"<strong>{titre}</strong>"
                f'<span style="font-size:.75rem;opacity:.6;"> · {c["type"]} · {html.escape(cible)}'
                f" · {c['nb_entrees']} entrée(s)</span></div>",
                unsafe_allow_html=True,
            )
            if c["description"]:
                st.markdown(
                    f'<div style="white-space:pre-wrap;font-size:.88rem;margin:6px 0;">'
                    f"{html.escape(c['description'])}</div>",
                    unsafe_allow_html=True,
                )

            nouveau = st.selectbox(
                "Statut",
                npt.STATUTS_CHANTIER,
                index=npt.STATUTS_CHANTIER.index(c["statut"]),
                key=f"npt_ch_statut_{c['id']}",
            )
            if nouveau != c["statut"]:
                npt.changer_statut_chantier(c["id"], nouveau)
                st.rerun()

            for e in npt.entrees(c["id"]):
                st.markdown(
                    f'<div style="border-left:2px solid {color}40;padding:6px 12px;'
                    f'margin:4px 0;font-size:.88rem;">'
                    f'<span style="font-size:.75rem;opacity:.55;">{e["date_entree"]}</span><br>'
                    f'<span style="white-space:pre-wrap;">{html.escape(e["contenu"])}</span></div>',
                    unsafe_allow_html=True,
                )

            with st.form(f"npt_ch_entree_{c['id']}", clear_on_submit=True):
                d = st.date_input("Date", value=today_local(), key=f"npt_ch_d_{c['id']}")
                texte = st.text_area(
                    "Entrée de suivi",
                    height=80,
                    key=f"npt_ch_t_{c['id']}",
                    placeholder="Réflexion, résultat d'un exercice, avancée, prise de conscience…",
                )
                if st.form_submit_button("Ajouter au suivi", use_container_width=True):
                    if not texte.strip():
                        st.warning("Écris quelque chose avant d'enregistrer.")
                    else:
                        npt.ajouter_entree(c["id"], d.isoformat(), texte.strip())
                        st.rerun()

    # ── Nouveau chantier ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Nouveau chantier")
    with st.form("npt_ch_new", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            cible = st.selectbox("Concerne", [_MOI, *noms.values()])
        with col_b:
            type_ = st.selectbox("Type", npt.TYPES_CHANTIER)
        titre = st.text_input("Titre", placeholder="Ex. : Pourquoi je m'éloigne quand ça se tend")
        desc = st.text_area("Description / point de départ (optionnel)", height=80)
        if st.form_submit_button("Créer le chantier", use_container_width=True):
            if not titre.strip():
                st.warning("Le titre est requis.")
            else:
                pid = next((i for i, n in noms.items() if n == cible), None)
                npt.ajouter_chantier(pid, type_, titre.strip(), desc.strip())
                st.rerun()
