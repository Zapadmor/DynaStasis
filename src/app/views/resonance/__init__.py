"""RÉSONNANCE : audits hebdomadaire, trimestriel, annuel et notes."""

from __future__ import annotations

import streamlit as st

from src.app.views.resonance.annuel import _render_audit_annuel
from src.app.views.resonance.hebdo import _render_audit_hebdo
from src.app.views.resonance.notes import _render_notes_trop_tard
from src.app.views.resonance.trimestriel import _render_audit_trimestriel

# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render(current_week: dict | None) -> None:
    st.header("RÉSONNANCE — Écrits & Profondeur")

    tab_hebdo, tab_trim, tab_annuel, tab_notes = st.tabs(
        [
            "Audit hebdo",
            "Audit trimestriel",
            "Audit annuel",
            "Notes pour trop tard",
        ]
    )

    with tab_hebdo:
        _render_audit_hebdo(current_week)

    with tab_trim:
        _render_audit_trimestriel()

    with tab_annuel:
        _render_audit_annuel()

    with tab_notes:
        _render_notes_trop_tard()
