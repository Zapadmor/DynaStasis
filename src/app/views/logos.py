from __future__ import annotations

import streamlit as st

from src.app.components import PALETTE
from src.core.profile import get_profile
from src.database.connection import db_session

# ── GPA — valeurs initiales neutres ; le relevé réel est persisté dans `logos_gpa` ──

_GPA_DEFAULTS = {
    "tc_gpa": 0.0,
    "tc_uvs": 0,
    "branche_gpa": 0.0,
    "branche_uvs": 0,
    "global_gpa": 0.0,
    "global_uvs": 0,
    "cible_gpa": 4.0,
    "cible_uvs": 0,
    "cs_gpa": 0.0,
    "cs_uvs": 0,
    "tm_gpa": 0.0,
    "tm_uvs": 0,
    "tsh_gpa": 0.0,
    "tsh_uvs": 0,
    "semestres_passes": 0,
}


# ─────────────────────────────────────────────────────────────────────────────
# ONGLET CURSUS
# ─────────────────────────────────────────────────────────────────────────────


def _load_gpa(conn) -> dict:
    row = conn.execute("SELECT * FROM logos_gpa WHERE id = 1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO logos_gpa "
            "(id, tc_gpa, tc_uvs, branche_gpa, branche_uvs, global_gpa, global_uvs, "
            "cible_gpa, cible_uvs, cs_gpa, cs_uvs, tm_gpa, tm_uvs, tsh_gpa, tsh_uvs, "
            "semestres_passes, updated_at) "
            "VALUES (1, :tc_gpa, :tc_uvs, :branche_gpa, :branche_uvs, :global_gpa, :global_uvs, "
            ":cible_gpa, :cible_uvs, :cs_gpa, :cs_uvs, :tm_gpa, :tm_uvs, :tsh_gpa, :tsh_uvs, "
            ":semestres_passes, datetime('now'))",
            _GPA_DEFAULTS,
        )
        row = conn.execute("SELECT * FROM logos_gpa WHERE id = 1").fetchone()
    return dict(row)


def _save_gpa(conn, values: dict) -> None:
    values = {**values, "id": 1}
    conn.execute(
        "UPDATE logos_gpa SET "
        "tc_gpa=:tc_gpa, tc_uvs=:tc_uvs, branche_gpa=:branche_gpa, branche_uvs=:branche_uvs, "
        "global_gpa=:global_gpa, global_uvs=:global_uvs, cible_gpa=:cible_gpa, cible_uvs=:cible_uvs, "
        "cs_gpa=:cs_gpa, cs_uvs=:cs_uvs, tm_gpa=:tm_gpa, tm_uvs=:tm_uvs, "
        "tsh_gpa=:tsh_gpa, tsh_uvs=:tsh_uvs, semestres_passes=:semestres_passes, "
        "updated_at=datetime('now') "
        "WHERE id=:id",
        values,
    )


def _tab_cursus() -> None:
    import pandas as pd

    # ── GPA — tableau compact + édition repliable ───────────────────────────
    with db_session() as conn:
        gpa = _load_gpa(conn)

    st.markdown(f"### {get_profile('logos.cursus_titre', 'Cursus académique')}")
    st.caption(f"Dernière mise à jour : {gpa.get('updated_at') or '—'}")

    df_gpa = pd.DataFrame(
        [
            {
                "Tronc Commun": f"{gpa['tc_gpa']:.2f} ({gpa['tc_uvs']} UVs)",
                "Branche": f"{gpa['branche_gpa']:.2f} ({gpa['branche_uvs']} UVs)",
                "Global": f"{gpa['global_gpa']:.2f} ({gpa['global_uvs']} UVs)",
                "Cible": f"{gpa['cible_gpa']:.2f} ({gpa['cible_uvs']} UVs)",
                "CS": f"{gpa['cs_gpa']:.2f} ({gpa['cs_uvs']} UVs)",
                "TM": f"{gpa['tm_gpa']:.2f} ({gpa['tm_uvs']} UVs)",
                "TSH": f"{gpa['tsh_gpa']:.2f} ({gpa['tsh_uvs']} UVs)",
            }
        ]
    )
    st.dataframe(df_gpa, use_container_width=True, hide_index=True)
    ecart = gpa["global_gpa"] - gpa["cible_gpa"]
    st.caption(
        f"Semestres passés (hors stages, hors étranger) : **{gpa['semestres_passes']}** "
        f"· Écart Global → Cible : {ecart:+.2f}"
    )

    with st.expander("✏️ Modifier les GPA"):
        with st.form("form_gpa"):
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                tc_gpa = st.number_input(
                    "GPA Tronc Commun", value=float(gpa["tc_gpa"]), step=0.01, format="%.2f"
                )
                tc_uvs = st.number_input(
                    "UVs Tronc Commun", value=int(gpa["tc_uvs"]), step=1, min_value=0
                )
            with col_b:
                branche_gpa = st.number_input(
                    "GPA Branche", value=float(gpa["branche_gpa"]), step=0.01, format="%.2f"
                )
                branche_uvs = st.number_input(
                    "UVs Branche", value=int(gpa["branche_uvs"]), step=1, min_value=0
                )
            with col_c:
                global_gpa = st.number_input(
                    "GPA Global", value=float(gpa["global_gpa"]), step=0.01, format="%.2f"
                )
                global_uvs = st.number_input(
                    "UVs Global", value=int(gpa["global_uvs"]), step=1, min_value=0
                )
            with col_d:
                cible_gpa = st.number_input(
                    "GPA Cible", value=float(gpa["cible_gpa"]), step=0.01, format="%.2f"
                )
                cible_uvs = st.number_input(
                    "UVs Cible", value=int(gpa["cible_uvs"]), step=1, min_value=0
                )

            col_e, col_f, col_g, col_h = st.columns(4)
            with col_e:
                cs_gpa = st.number_input(
                    "GPA CS", value=float(gpa["cs_gpa"]), step=0.01, format="%.2f"
                )
                cs_uvs = st.number_input("UVs CS", value=int(gpa["cs_uvs"]), step=1, min_value=0)
            with col_f:
                tm_gpa = st.number_input(
                    "GPA TM", value=float(gpa["tm_gpa"]), step=0.01, format="%.2f"
                )
                tm_uvs = st.number_input("UVs TM", value=int(gpa["tm_uvs"]), step=1, min_value=0)
            with col_g:
                tsh_gpa = st.number_input(
                    "GPA TSH", value=float(gpa["tsh_gpa"]), step=0.01, format="%.2f"
                )
                tsh_uvs = st.number_input("UVs TSH", value=int(gpa["tsh_uvs"]), step=1, min_value=0)
            with col_h:
                semestres_passes = st.number_input(
                    "Semestres passés", value=int(gpa["semestres_passes"]), step=1, min_value=0
                )

            submitted = st.form_submit_button("💾 Enregistrer les GPA")

        if submitted:
            with db_session() as conn:
                _save_gpa(
                    conn,
                    {
                        "tc_gpa": tc_gpa,
                        "tc_uvs": tc_uvs,
                        "branche_gpa": branche_gpa,
                        "branche_uvs": branche_uvs,
                        "global_gpa": global_gpa,
                        "global_uvs": global_uvs,
                        "cible_gpa": cible_gpa,
                        "cible_uvs": cible_uvs,
                        "cs_gpa": cs_gpa,
                        "cs_uvs": cs_uvs,
                        "tm_gpa": tm_gpa,
                        "tm_uvs": tm_uvs,
                        "tsh_gpa": tsh_gpa,
                        "tsh_uvs": tsh_uvs,
                        "semestres_passes": semestres_passes,
                    },
                )
            st.success("GPA mis à jour.")
            st.rerun()

    st.markdown("---")

    # ── Historique des UVs suivies — éditable ───────────────────────────────
    st.markdown("#### Historique des UVs suivies")
    with db_session() as conn:
        rows = conn.execute(
            "SELECT semestre, code, intitule, type_uv, credits, note, en_cours, valide "
            "FROM cours_ecole WHERE semestre IS NOT NULL ORDER BY id, code"
        ).fetchall()

    df_hist = pd.DataFrame(
        [
            {
                "Semestre": r["semestre"],
                "UV": r["code"],
                "Intitulé": r["intitule"],
                "Type": r["type_uv"],
                "Crédits": r["credits"],
                "Note": r["note"],
                "En cours": bool(r["en_cours"]),
                "Validé": bool(r["valide"]),
            }
            for r in rows
        ]
    )
    if not df_hist.empty:
        total_credits = df_hist.loc[~df_hist["En cours"], "Crédits"].sum()
        st.caption(f"Total crédits (hors UVs en cours) : {total_credits:.0f}")

    edited_hist = st.data_editor(
        df_hist,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Crédits": st.column_config.NumberColumn(min_value=0, step=1),
            "En cours": st.column_config.CheckboxColumn(),
            "Validé": st.column_config.CheckboxColumn(),
        },
        key="editor_historique_ecole",
    )

    if st.button("💾 Enregistrer l'historique", key="save_historique_ecole"):
        new_rows = [
            (
                r["Semestre"],
                r["UV"],
                r["Intitulé"],
                r["Type"],
                None if pd.isna(r["Crédits"]) else int(r["Crédits"]),
                r["Note"] if isinstance(r["Note"], str) and r["Note"] else None,
                int(bool(r["En cours"])),
                int(bool(r["Validé"])),
            )
            for r in edited_hist.to_dict("records")
            if r.get("Semestre") and r.get("UV")
        ]
        try:
            with db_session() as conn:
                conn.execute("DELETE FROM cours_ecole WHERE semestre IS NOT NULL")
                conn.executemany(
                    "INSERT INTO cours_ecole (semestre, code, intitule, type_uv, credits, note, en_cours, valide) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    new_rows,
                )
            st.success("Historique mis à jour.")
            st.rerun()
        except Exception as exc:
            st.error(f"Échec de l'enregistrement (doublon Semestre+UV ?) : {exc}")

    st.markdown("---")

    # ── Catalogue GI — éditable ──────────────────────────────────────────────
    st.markdown("#### Catalogue des UVs")
    with db_session() as conn:
        cat_rows = conn.execute(
            "SELECT code, intitule, type_uv, credits, disponibilite, competences, en_cours, valide "
            "FROM cours_ecole WHERE semestre IS NULL ORDER BY code"
        ).fetchall()

    df_cat = pd.DataFrame(
        [
            {
                "UV": r["code"],
                "Intitulé": r["intitule"],
                "Type": r["type_uv"],
                "Crédits": r["credits"],
                "Disponibilité": r["disponibilite"],
                "Compétences": r["competences"],
                "En cours": bool(r["en_cours"]),
                "Validé": bool(r["valide"]),
            }
            for r in cat_rows
        ]
    )

    edited_cat = st.data_editor(
        df_cat,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Crédits": st.column_config.NumberColumn(min_value=0, step=1),
            "En cours": st.column_config.CheckboxColumn(),
            "Validé": st.column_config.CheckboxColumn(),
        },
        key="editor_catalogue_ecole",
    )

    if st.button("💾 Enregistrer le catalogue", key="save_catalogue_ecole"):
        new_cat_rows = [
            (
                r["UV"],
                r["Intitulé"],
                r["Type"],
                None if pd.isna(r["Crédits"]) else int(r["Crédits"]),
                r["Disponibilité"]
                if isinstance(r["Disponibilité"], str) and r["Disponibilité"]
                else None,
                r["Compétences"]
                if isinstance(r["Compétences"], str) and r["Compétences"]
                else None,
                int(bool(r["En cours"])),
                int(bool(r["Validé"])),
            )
            for r in edited_cat.to_dict("records")
            if r.get("UV") and r.get("Intitulé")
        ]
        try:
            with db_session() as conn:
                conn.execute("DELETE FROM cours_ecole WHERE semestre IS NULL")
                conn.executemany(
                    "INSERT INTO cours_ecole "
                    "(semestre, code, intitule, type_uv, credits, disponibilite, competences, en_cours, valide) "
                    "VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                    new_cat_rows,
                )
            st.success("Catalogue mis à jour.")
            st.rerun()
        except Exception as exc:
            st.error(f"Échec de l'enregistrement (UV en doublon ?) : {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# ONGLET PLAN DE CARRIÈRE
# ─────────────────────────────────────────────────────────────────────────────


def _render_bloc(bloc: dict) -> None:
    if bloc.get("titre"):
        st.markdown(bloc["titre"])
    kind = bloc.get("type")
    if kind == "bullets":
        for titre, detail in bloc["items"]:
            st.markdown(f"· **{titre}** — {detail}")
    elif kind == "paragraphs":
        for titre, detail in bloc["items"]:
            st.markdown(f"**{titre}** — {detail}")
    elif kind == "cards":
        for titre, detail in bloc["items"]:
            st.markdown(f"**{titre}**")
            st.markdown(f"<span style='font-size:.88rem;'>{detail}</span>", unsafe_allow_html=True)
    elif kind == "table":
        try:
            import pandas as pd

            st.dataframe(pd.DataFrame(bloc["rows"]), use_container_width=True, hide_index=True)
        except Exception:
            for row in bloc["rows"]:
                st.text(" : ".join(str(v) for v in row.values()))


def _tab_carriere() -> None:
    """Plan de carrière piloté par la base (clé `logos.plan_carriere`, format JSON générique)."""
    plan = get_profile("logos.plan_carriere")
    if not plan:
        st.info(
            "Aucun plan de carrière renseigné. Importer un plan JSON dans la table "
            "`profil_contenu` (clé `logos.plan_carriere`) — voir la documentation."
        )
        return

    st.markdown(f"### {plan['titre']}")
    if plan.get("sous_titre"):
        st.caption(plan["sous_titre"])
    if plan.get("meta"):
        st.markdown("  \n".join(plan["meta"]))

    encart = plan.get("encart")
    if encart:
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["blue_green"]};padding:8px 14px;margin:12px 0;">'
            f"<strong>{encart['titre']}</strong><br>"
            f'<span style="font-size:.88rem;">{encart["texte"]}</span></div>',
            unsafe_allow_html=True,
        )

    for section in plan.get("sections", []):
        st.markdown("---")
        st.markdown(f"#### {section['titre']}")
        for ligne in section.get("intro", []):
            st.markdown(ligne)
        for bloc in section.get("blocs", []):
            _render_bloc(bloc)

    if plan.get("citation"):
        st.markdown("---")
        st.markdown(
            f'<p style="text-align:center;font-style:italic;color:{PALETTE["amber"]};">'
            f"« {plan['citation']} »</p>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render(current_week: dict | None) -> None:
    st.header("LOGOS — Connaissance & Carrière")

    tab_cursus, tab_car = st.tabs(["Cursus", "Plan de Carrière"])

    with tab_cursus:
        _tab_cursus()

    with tab_car:
        _tab_carriere()
