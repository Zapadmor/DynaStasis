"""Onglet « Audit annuel »."""

from __future__ import annotations

import streamlit as st

from src.app.components import PALETTE
from src.app.views.resonance.gabarits import _ANNUEL_M5, _ANNUEL_MODULES
from src.core.tz import today_local
from src.services import audits

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 : AUDIT ANNUEL
# ─────────────────────────────────────────────────────────────────────────────


def _render_audit_annuel() -> None:
    st.markdown("### Audit Annuel de Clarté & d'Alignement Personnel")
    st.caption(
        "Cadre méthodologique : psychologie comportementale, Théorie de l'Autodétermination "
        "(Deci & Ryan), Théorie de l'Acceptation et de l'Engagement (ACT) et neurosciences "
        "appliquées. Ce protocole remplace l'autocritique moralisante par une observation "
        "clinique et factuelle — réponds avec honnêteté, sans complaisance ni autoflagellation."
    )

    today = today_local()
    annee = st.number_input(
        "Année de l'audit",
        min_value=2024,
        max_value=2040,
        value=today.year,
        step=1,
        key="annuel_annee",
    )
    date_audit = st.date_input("Date de réalisation", value=today, key="annuel_date")

    if not audits.table_prete("audit_annuel"):
        st.info("Table non initialisée. Lancez `python main.py init-db`.")
        return
    ex = audits.annuel(annee)

    annee_int = int(annee)
    all_vals: dict[str, object] = {}

    with st.form(f"audit_annuel_form_{annee_int}"):
        for module in _ANNUEL_MODULES:
            st.markdown(
                f'<div style="border-left:3px solid {module["color"]};'
                f'padding:4px 14px;margin:18px 0 10px;">'
                f"<strong>{module['title']}</strong><br>"
                f'<span style="font-size:.82rem;opacity:.75;">{module["objectif"]}</span></div>',
                unsafe_allow_html=True,
            )

            cols = st.columns(4)
            for (field_key, label, hint), col in zip(module["indicators"], cols, strict=True):
                with col:
                    all_vals[field_key] = st.number_input(
                        label,
                        min_value=1,
                        max_value=5,
                        value=int(ex.get(field_key) or 3),
                        step=1,
                        help=hint,
                        key=f"annuel_{annee_int}_{field_key}",
                    )
            score = audits.score_module_annuel(ex, module)
            st.caption(
                f"Score du Pilier (dernier enregistrement) : {score} / 20"
                if score is not None
                else "Score du Pilier : pas encore enregistré."
            )

            for field_key, label, hint in module["questions"]:
                st.caption(f"**{label}** — {hint}")
                all_vals[field_key] = st.text_area(
                    label,
                    value=ex.get(field_key) or "",
                    height=90,
                    key=f"annuel_{annee_int}_{field_key}",
                    label_visibility="collapsed",
                    placeholder="Ta réponse ici…",
                )

        # Module 5 — structure dédiée (piliers + intentions Si/Alors)
        st.markdown(
            f'<div style="border-left:3px solid {_ANNUEL_M5["color"]};'
            f'padding:4px 14px;margin:18px 0 10px;">'
            f"<strong>{_ANNUEL_M5['title']}</strong><br>"
            f'<span style="font-size:.82rem;opacity:.75;">{_ANNUEL_M5["objectif"]}</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown("**5.1 Définition des 3 piliers clés (12 mois)**")
        for obj_key, ind_key, label in _ANNUEL_M5["piliers"]:
            st.caption(label)
            col_obj, col_ind = st.columns(2)
            with col_obj:
                all_vals[obj_key] = st.text_input(
                    "Objectif",
                    value=ex.get(obj_key) or "",
                    key=f"annuel_{annee_int}_{obj_key}",
                )
            with col_ind:
                all_vals[ind_key] = st.text_input(
                    "Indicateur de succès",
                    value=ex.get(ind_key) or "",
                    key=f"annuel_{annee_int}_{ind_key}",
                )

        st.markdown("**5.2 Architecture des comportements — Intentions « Si / Alors »**")
        for decl_key, comp_key, label, decl_hint, comp_hint in _ANNUEL_M5["si_alors"]:
            st.caption(label)
            col_si, col_alors = st.columns(2)
            with col_si:
                all_vals[decl_key] = st.text_input(
                    "SI…",
                    value=ex.get(decl_key) or "",
                    placeholder=decl_hint,
                    key=f"annuel_{annee_int}_{decl_key}",
                )
            with col_alors:
                all_vals[comp_key] = st.text_input(
                    "ALORS…",
                    value=ex.get(comp_key) or "",
                    placeholder=comp_hint,
                    key=f"annuel_{annee_int}_{comp_key}",
                )

        # Synthèse du bilan annuel
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};'
            f'padding:4px 14px;margin:18px 0 10px;">'
            f"<strong>Synthèse du Bilan Annuel</strong></div>",
            unsafe_allow_html=True,
        )
        total_score = 0
        total_known = True
        for module in _ANNUEL_MODULES:
            s = audits.score_module_annuel(ex, module)
            if s is None:
                total_known = False
            else:
                total_score += s
        st.caption(
            f"Total général de maturité comportementale (dernier enregistrement) : "
            f"{total_score if total_known else '—'} / 80"
        )
        col_o1, col_o2, col_o3, col_o4 = st.columns(4)
        objectif_cols = [col_o1, col_o2, col_o3, col_o4]
        for module, col in zip(_ANNUEL_MODULES, objectif_cols, strict=True):
            okey = f"objectif_{module['key']}"
            with col:
                all_vals[okey] = st.number_input(
                    f"Objectif suivant — {module['title'].split('—')[0].strip()}",
                    min_value=0,
                    max_value=20,
                    value=int(ex.get(okey) or 0),
                    step=1,
                    key=f"annuel_{annee_int}_{okey}",
                )

        all_vals["date_audit"] = date_audit.isoformat()

        submitted = st.form_submit_button(f"Sauvegarder — Audit {annee}", use_container_width=True)

    if submitted:
        try:
            audits.sauvegarder_annuel(annee, all_vals)
            st.success(f"Audit {annee} enregistré.")
            st.rerun()
        except Exception as exc:
            st.error(f"Erreur : {exc}")

    # Liste des années enregistrées
    years = audits.historique_annuel()

    if years:
        st.markdown("---")
        st.markdown("#### Années enregistrées")
        cols = st.columns(min(len(years), 5))
        for i, y in enumerate(years):
            y_dict = dict(y)
            total = 0
            total_known = True
            for module in _ANNUEL_MODULES:
                s = audits.score_module_annuel(y_dict, module)
                if s is None:
                    total_known = False
                else:
                    total += s
            score_label = f"{total} / 80" if total_known else "—"
            with cols[i % 5]:
                label = y["date_audit"] or str(y["annee"])
                st.markdown(
                    f'<div style="border-left:2px solid {PALETTE["amber"]};'
                    f'padding:4px 10px;font-size:.85rem;">'
                    f"<strong>{y['annee']}</strong><br>"
                    f'<span style="font-size:.75rem;opacity:.65;">{label}</span><br>'
                    f'<span style="font-size:.75rem;opacity:.65;">{score_label}</span></div>',
                    unsafe_allow_html=True,
                )
