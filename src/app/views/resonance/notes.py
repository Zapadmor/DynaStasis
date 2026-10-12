"""Onglet « Notes pour trop tard »."""

from __future__ import annotations

import streamlit as st

from src.app.components import GRAY, PALETTE
from src.core.tz import today_local
from src.services import npt

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 : NOTES POUR TROP TARD
# ─────────────────────────────────────────────────────────────────────────────

_ETAT_COLORS = {
    "En vie et proche": PALETTE["blue_green"],
    "En vie et distant": PALETTE["sky_blue"],
    "Mort": GRAY,
}
_ETAT_ORDER = ["En vie et proche", "Mort", "En vie et distant", ""]
_LIEN_COLORS = {
    "Famille": PALETTE["amber"],
    "Amour": "#b84c8e",
    "Amis": PALETTE["blue_green"],
    "Complexe": GRAY,
}


def _render_notes_trop_tard() -> None:
    st.markdown("### Notes pour trop tard — Mémoire & Présences")
    st.caption("Pour les personnes qui comptent et celles qui ne sont plus là.")

    if not npt.tables_pretes():
        st.info("Tables non initialisées. Lancez `python main.py init-db`.")
        return

    persons = npt.personnes()

    if not persons:
        st.info("Aucune personne enregistrée. Utilise le formulaire ci-dessous.")

    # ── Liste des personnes ──────────────────────────────────────────────────
    for etat_groupe in ["En vie et proche", "Mort", "En vie et distant"]:
        groupe = [p for p in persons if p["etat"] == etat_groupe]
        if not groupe:
            continue
        color = _ETAT_COLORS.get(etat_groupe, GRAY)
        st.markdown(
            f'<div style="border-left:3px solid {color};padding:3px 14px;margin:18px 0 10px;">'
            f'<strong style="font-size:.9rem;text-transform:uppercase;letter-spacing:.08em;">'
            f"{etat_groupe}</strong></div>",
            unsafe_allow_html=True,
        )

        for person in groupe:
            pid = person["id"]
            full_name = f"{person['prenom']} {person['nom']}".strip()
            liens_list = [
                lien.strip() for lien in (person["liens"] or "").split(",") if lien.strip()
            ]
            liens_html = " ".join(
                f'<span style="font-size:.72rem;padding:1px 6px;border-radius:3px;'
                f'background:{_LIEN_COLORS.get(lien, GRAY)}22;color:{_LIEN_COLORS.get(lien, GRAY)};">'
                f"{lien}</span>"
                for lien in liens_list
            )
            prox_html = (
                f'<span style="font-size:.78rem;opacity:.6;">{person["proximite"]}%</span>'
                if person["proximite"] is not None
                else ""
            )
            st.markdown(
                f'<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:4px;">'
                f'<span style="font-size:1rem;">{full_name}</span>'
                f"{liens_html}{prox_html}</div>",
                unsafe_allow_html=True,
            )

            notes = npt.notes(pid)
            with st.expander(f"Notes ({len(notes)})"):
                for note in notes:
                    date_display = note.get("date_note") or "—"
                    contenu = note.get("contenu", "")
                    st.markdown(
                        f'<div style="border-left:2px solid {color}40;padding:6px 12px;'
                        f'margin:4px 0;font-size:.88rem;">'
                        f'<span style="font-size:.75rem;opacity:.55;">{date_display}</span><br>'
                        f'<span style="white-space:pre-wrap;">{contenu}</span></div>',
                        unsafe_allow_html=True,
                    )
                if not notes:
                    st.caption("Aucune note pour cette personne.")

            st.markdown(
                '<hr style="border:none;border-top:1px solid #8ecae620;margin:6px 0;">',
                unsafe_allow_html=True,
            )

    # ── Ajouter une entrée ───────────────────────────────────────────────────
    if persons:
        st.markdown("---")
        st.markdown("#### Ajouter une entrée")
        person_labels = [f"{p['prenom']} {p['nom']}".strip() for p in persons]
        person_ids = [p["id"] for p in persons]

        with st.form("npt_add_note_form"):
            col_sel, col_date = st.columns([2, 1])
            with col_sel:
                selected_idx = st.selectbox(
                    "Personne",
                    range(len(person_labels)),
                    format_func=lambda i: person_labels[i],
                )
            with col_date:
                note_date = st.date_input("Date", value=today_local())
            new_note = st.text_area(
                "Note",
                height=90,
                placeholder="Ce que je ressens, un souvenir, une pensée…",
            )
            if st.form_submit_button("Ajouter au journal", use_container_width=True):
                if not new_note.strip():
                    st.warning("Écris quelque chose avant d'enregistrer.")
                else:
                    npt.ajouter_note(
                        person_ids[selected_idx],
                        note_date.isoformat(),
                        new_note.strip(),
                    )
                    st.success(f"Note ajoutée pour {person_labels[selected_idx]}.")
                    st.rerun()

    # ── Nouvelle personne ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Nouvelle personne")

    with st.form("npt_new_person_form"):
        col_fn, col_ln = st.columns(2)
        with col_fn:
            new_prenom = st.text_input("Prénom")
        with col_ln:
            new_nom = st.text_input("Nom")
        col_l, col_e, col_p = st.columns(3)
        with col_l:
            new_liens = st.multiselect("Lien avec toi", ["Famille", "Amour", "Amis", "Complexe"])
        with col_e:
            new_etat = st.selectbox("État", ["En vie et proche", "En vie et distant", "Mort"])
        with col_p:
            new_prox = st.number_input("Proximité (%)", 0, 100, value=50)
        new_intro = st.text_area("Note initiale (optionnel)", height=80)
        if st.form_submit_button("Créer", use_container_width=True):
            if not new_prenom.strip():
                st.warning("Le prénom est requis.")
            else:
                new_id = npt.ajouter_personne(
                    new_prenom.strip(),
                    new_nom.strip(),
                    new_liens,
                    new_etat,
                    int(new_prox),
                )
                if new_intro.strip():
                    npt.ajouter_note(new_id, today_local().isoformat(), new_intro.strip())
                st.success(f"{new_prenom.strip()} ajouté(e).")
                st.rerun()
