"""Onglet « Audit trimestriel »."""

from __future__ import annotations

import streamlit as st

from src.app.components import PALETTE
from src.app.views.resonance.gabarits import _SAISON_PAR_MOIS, _SAISONS, _TRIM_PARTIES
from src.core.tz import today_local
from src.services import audits

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 : AUDIT TRIMESTRIEL
# ─────────────────────────────────────────────────────────────────────────────


def _render_audit_trimestriel() -> None:
    st.markdown("### Audit Trimestriel — Bilan & Intentions")

    today = today_local()
    saison_defaut = _SAISON_PAR_MOIS.get(today.month, "Printemps")

    col_s, col_y = st.columns([2, 1])
    with col_s:
        saison = st.selectbox(
            "Saison", _SAISONS, index=_SAISONS.index(saison_defaut), key="trim_saison"
        )
    with col_y:
        annee = st.number_input(
            "Année", min_value=2024, max_value=2040, value=today.year, step=1, key="trim_annee"
        )

    if not audits.table_prete("audit_trimestriel"):
        st.info("Table non initialisée. Lancez `python main.py init-db`.")
        return
    ex = audits.trimestriel(saison, annee)

    st.markdown("")

    all_vals: dict[str, str] = {}
    annee_int = int(annee)

    with st.form(f"audit_trim_form_{saison}_{annee_int}"):
        for partie in _TRIM_PARTIES:
            st.markdown(
                f'<div style="border-left:3px solid {partie["color"]};padding:4px 14px;margin:14px 0 10px;">'
                f"<strong>{partie['title']}</strong></div>",
                unsafe_allow_html=True,
            )
            for field_key, label, hint in partie["champs"]:
                st.caption(hint)
                all_vals[field_key] = st.text_area(
                    label,
                    value=ex.get(field_key) or "",
                    height=110,
                    key=f"trim_{saison}_{annee_int}_{field_key}",
                )

        submitted = st.form_submit_button(
            f"Sauvegarder — {saison} {annee}", use_container_width=True
        )

    if submitted:
        try:
            audits.sauvegarder_trimestriel(saison, annee, all_vals)
            st.success(f"Audit {saison} {annee} enregistré.")
            st.rerun()
        except Exception as exc:
            st.error(f"Erreur : {exc}")

    # Historique des audits trimestriels
    hist = audits.historique_trimestriel()
    if hist:
        st.markdown("---")
        st.markdown("#### Audits précédents")
        cols = st.columns(min(len(hist), 4))
        for i, h in enumerate(hist):
            with cols[i % 4]:
                st.markdown(
                    f'<div style="border-left:2px solid {PALETTE["blue_green"]};'
                    f'padding:4px 10px;font-size:.85rem;">'
                    f"<strong>{h['saison']} {h['annee']}</strong></div>",
                    unsafe_allow_html=True,
                )
