"""Onglet « Audit hebdo »."""

from __future__ import annotations

import streamlit as st

from src.app.components import GRAY, PALETTE
from src.app.theme import contrast_text as _contrast_text
from src.app.theme import is_dark as _is_dark
from src.core import user_config
from src.core.focus_manager import forge_tag_for_mode
from src.core.profile import get_profile
from src.services import audits

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 : AUDIT HEBDOMADAIRE (Sections II–VI)
# ─────────────────────────────────────────────────────────────────────────────


def _render_audit_hebdo(current_week: dict | None) -> None:
    st.markdown("### Audit Hebdomadaire — Template Complet")

    if not audits.table_prete("audit_narrative"):
        st.info("Table `audit_narrative` non initialisée. Lancez `python main.py init-db`.")
        return
    all_weeks = audits.semaines_recentes(52)

    if not all_weeks:
        st.info("Aucune semaine disponible.")
        return

    week_ids = [w["id"] for w in all_weeks]
    week_labels = {w["id"]: w["week_label"] for w in all_weeks}
    week_starts = {w["id"]: w["week_start"] for w in all_weeks}
    default_idx = 0
    if current_week and current_week["id"] in week_ids:
        default_idx = week_ids.index(current_week["id"])

    selected_id = st.selectbox(
        "Semaine",
        options=week_ids,
        format_func=lambda x: week_labels[x],
        index=default_idx,
        key="audit_hebdo_week_sel",
    )

    # Per-week data key: loads fresh when week changes (key not in session_state)
    _data_key = f"_ah_data_{selected_id}"
    if _data_key not in st.session_state:
        with st.spinner("Chargement…"):
            st.session_state[_data_key] = audits.charger_audit(selected_id)

    d = st.session_state[_data_key]

    _sync_key = f"_sync_result_{selected_id}"

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        st.markdown(f"**{week_labels[selected_id]}**")
    with col_btn:
        if st.button("⟳ Synchroniser", key=f"sync_{selected_id}", use_container_width=True):
            with st.spinner("Synchronisation…"):
                try:
                    st.session_state[_sync_key] = audits.synchroniser_metriques(selected_id)
                except Exception as exc:
                    st.session_state[_sync_key] = {"error": str(exc)}
            st.session_state.pop(_data_key, None)
            st.rerun()

    if _sync_key in st.session_state:
        sync_res = st.session_state[_sync_key]
        if "error" in sync_res:
            st.error(f"Sync échoué : {sync_res['error']}")
        else:
            sa = sync_res.get("semaine", {})
            sc = sync_res.get("score", {})
            score = sc.get("score_semaine")

            score_color = (
                PALETTE["blue_green"]
                if (score or 0) >= 67
                else PALETTE["amber"]
                if (score or 0) >= 34
                else "#e05252"
            )

            def _fmt(v, suffix="", digits=1):
                return f"{round(float(v), digits)}{suffix}" if v is not None else "—"

            def _sleep_fmt(v):
                if v is None:
                    return "—"
                h, m = divmod(int(round(float(v))), 60)
                return f"{h}h{m:02d}"

            def _pill(ok, label, detail=""):
                if _is_dark():
                    bg = "#1a3a2a" if ok else "#3a1a1a"
                else:
                    bg = "#c8eec8" if ok else "#eec8c8"
                mark_col = PALETTE["blue_green"] if ok else "#e05252"
                pill_text = _contrast_text(bg)
                mark = "✓" if ok else "✗"
                detail_html = (
                    f' <span style="opacity:.55;font-size:.71rem;">({detail})</span>'
                    if detail
                    else ""
                )
                return (
                    f'<span style="background:{bg};border:1px solid {mark_col}33;'
                    f'border-radius:4px;padding:2px 8px;font-size:.79rem;white-space:nowrap;color:{pill_text};">'
                    f'<span style="color:{mark_col};font-weight:700;">{mark}</span>'
                    f" {label}{detail_html}</span>"
                )

            seuils = user_config.load()["seuils"]["semaine"]
            sommeil_h, sommeil_m = divmod(int(seuils["sommeil_min"]), 60)
            pills = [
                _pill(
                    sc.get("ok_entrainement"),
                    "Entraîn.",
                    f"{int(sc.get('entrainement_min', 0))}/{seuils['entrainement_min']:.0f}min",
                ),
                _pill(
                    sc.get("ok_seances"),
                    "Séances",
                    f"{int(sc.get('seances', 0))}/{seuils['seances']:.0f}",
                ),
                _pill(
                    sc.get("ok_pas"),
                    "Pas",
                    f"{int(sc.get('pas_total', 0)) // 1000}k/{seuils['pas'] / 1000:.0f}k",
                ),
                _pill(
                    sc.get("ok_sommeil"),
                    "Sommeil moy./nuit",
                    f"{_sleep_fmt(sc.get('sleep_moy'))}/{sommeil_h}h{sommeil_m:02d}",
                ),
                _pill(
                    sc.get("ok_charge_fraicheur"),
                    "Charge/Fraîch.",
                    f"TSB {_fmt(sc.get('tsb'), digits=1)}"
                    + (" · décharge" if sc.get("is_deload_week") else ""),
                ),
                _pill(
                    sc.get("ok_ecran"),
                    "Écran",
                    f"{int(sc.get('screen_distraction_min', 0))}/{seuils['ecran_max_min']:.0f}min",
                ),
                _pill(sc.get("ok_deep_focus"), "Focus", f"{int(sc.get('deep_focus_min', 0))}min"),
                _pill(
                    sc.get("ok_projets_fond"),
                    "Projets fond",
                    f"{int(sc.get('focus_projets_fond_min', 0))}/{seuils['projets_fond_min']:.0f}min",
                ),
                *(
                    [
                        _pill(
                            sc.get("ok_engagement"),
                            user_config.engagement_libelle(),
                            f"{int(sc.get('focus_engagement_min', 0))}min · "
                            f"{int(sc.get('jours_engagement_semaine', 0))}j",
                        )
                    ]
                    if user_config.engagement_actif()
                    else []
                ),
                _pill(sc.get("ok_cloture"), "Clôture", sc.get("social") or "—"),
            ]
            top = sa.get("top_apps_text") or "—"

            st.markdown(
                f'<div style="border-left:3px solid {score_color};padding:8px 14px;margin:6px 0;">'
                f'<div style="font-size:1rem;font-weight:700;color:{score_color};margin-bottom:6px;">'
                f"Score de la semaine : {_fmt(score, '/100', 0)}</div>"
                f'<div style="display:flex;gap:5px;flex-wrap:wrap;">' + " ".join(pills) + "</div>"
                f'<div style="font-size:.74rem;opacity:.55;margin-top:5px;">{top}</div>'
                "</div>",
                unsafe_allow_html=True,
            )

    # Charger le statut social + mode_actif depuis semaines_audit (absents de audit_narrative)
    _sa_meta = audits.meta_semaine(selected_id)
    _social_opts = ["Connecté/Ressourcé", "Isolé"]
    _social_current = (
        _sa_meta["social"] if _sa_meta and _sa_meta["social"] in _social_opts else _social_opts[0]
    )
    mode_actif = _sa_meta["mode_actif"] if _sa_meta else None

    _readouts_key = f"_ah_readouts_{selected_id}"
    if _readouts_key not in st.session_state:
        st.session_state[_readouts_key] = audits.lecture_audit(
            selected_id, week_starts[selected_id], mode_actif
        )
    readouts = st.session_state[_readouts_key]

    # ── Formulaire (sans key= sur les widgets : value= pilote tout) ───────────
    with st.form(f"audit_hebdo_form_{selected_id}"):
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};padding:4px 14px;margin-bottom:8px;">'
            f"<strong>II. ÉTAT DU SYSTÈME (STASIE)</strong></div>",
            unsafe_allow_html=True,
        )
        col_j, col_s, col_a = st.columns([2, 1.5, 1])
        with col_j:
            jauge = st.slider(
                "Jauge d'Énergie (1–10)",
                1,
                10,
                value=int(d.get("jauge_energie") or 6),
            )
        with col_s:
            social_val = st.selectbox(
                "Statut social",
                _social_opts,
                index=_social_opts.index(_social_current),
                help="Utilisé dans le critère #3 du score semaine.",
            )
        with col_a:
            alerte = st.checkbox(
                "Alerte Rouge",
                value=bool(d.get("alerte_rouge")),
                help="Ai-je menti sur mes actions ou raté un audit cette semaine ?",
            )
        correction = st.text_area(
            "Correction Immédiate (si alerte rouge)",
            value=d.get("correction_immediate") or "",
            height=60,
            placeholder="Définir l'action de réinitialisation…",
        )

        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["blue_green"]};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>III. LE PENTAGONE (DYNA)</strong></div>",
            unsafe_allow_html=True,
        )

        st.markdown("**VIGUEUR**")
        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.caption(f"Volume Course : {readouts['vigueur_volume_txt']}")
        col_v2.caption("Ratio Z2 vs Intensité : — (pas de source, sync Suunto à venir)")
        col_v3.caption(readouts["vigueur_hrv_sommeil_txt"])

        jours_mois = int(d.get("forge_jours_engagement_mois") or 0)
        jours_engagement_sem = int(d.get("jours_engagement_semaine") or 0)
        drill_eng = d.get("forge_drill_engagement") or ""
        if user_config.engagement_actif():
            libelle = user_config.engagement_libelle()
            libelle_jours = user_config.engagement_libelle_jours()
            st.markdown(f"**FORGE — {libelle}**")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                jours_mois = st.number_input(
                    f"{libelle_jours} ce mois-ci",
                    min_value=0,
                    max_value=31,
                    value=jours_mois,
                )
            with col_m2:
                jours_engagement_sem = st.number_input(
                    f"{libelle_jours} cette semaine",
                    min_value=0,
                    max_value=7,
                    value=jours_engagement_sem,
                )
            with col_m3:
                drill_eng = st.text_input(
                    "Pratique de la semaine",
                    value=drill_eng,
                    placeholder="Fait (X min) / Non fait",
                )
            st.caption(f"Temps focus dédié : {readouts['forge_engagement_txt']}")

        st.markdown("**FORGE — Hard Skills & Problématiques Critiques**")
        st.caption(f"Temps focus dédié : {readouts['forge_hardskills_txt']}")
        hardskills_sujet = st.text_input(
            "Sujet technique traité cette semaine",
            value=d.get("forge_hardskills_sujet") or "",
            placeholder="Ex. Optimisation mémoire C++20 / Pipeline TensorRT…",
        )

        # Initialisées avant le bloc conditionnel pour éviter tout NameError hors mode pro
        # (bloc entreprise non rendu, cf. §7 PLAN_AUDIT_HEBDO_V2.md).
        pro_champ_1 = d.get("forge_pro_champ_1")
        pro_champ_2 = d.get("forge_pro_champ_2")
        pro_champ_3 = d.get("forge_pro_champ_3")
        pro_blocage = d.get("forge_pro_blocage")
        pro_dep_tiers = bool(d.get("forge_pro_dependance_tiers"))

        pro_labels = get_profile(
            "audit.forge_pro_labels",
            ["Point 1 — avancement", "Point 2 — avancement", "Point 3 — avancement"],
        )
        if forge_tag_for_mode(mode_actif) == "FORGE_PRO":
            st.markdown("**FORGE — Entreprise**")
            st.caption(f"Temps focus dédié : {readouts['forge_pro_txt']}")
            pro_champ_1 = st.text_input(
                pro_labels[0],
                value=pro_champ_1 or "",
            )
            pro_champ_2 = st.text_input(
                pro_labels[1],
                value=pro_champ_2 or "",
            )
            pro_champ_3 = st.text_input(
                pro_labels[2],
                value=pro_champ_3 or "",
            )
            pro_blocage = st.text_area(
                "Blocage technique rencontré & solution apportée en solo",
                value=pro_blocage or "",
                height=70,
            )
            pro_dep_tiers = st.checkbox(
                "Ai-je eu besoin d'un tiers pour diagnostiquer/valider un problème hard/soft "
                "cette semaine ?",
                value=pro_dep_tiers,
                help="Cible : tendre vers Non.",
            )
            st.caption(f"Jalons de livraison : {readouts['forge_pro_jalons_txt'] or '—'}")

        st.markdown("**LOGOS — Académique & Recherche**")
        st.caption(f"Temps focus dédié : {readouts['logos_txt']}")
        logos_uvs = st.text_input(
            "Avancement UVs critiques / GPA",
            value=d.get("logos_avancement_uvs") or "",
            placeholder="Points durs traités / zéro retard sur rendus…",
        )
        logos_tx = st.text_input(
            "Projet TX & Publication",
            value=d.get("logos_projet_tx") or "",
            placeholder="État du banc de test / rédaction papier / échange enseignant-chercheur…",
        )
        logos_article = st.text_input(
            "Article scientifique analysé cette semaine",
            value=d.get("logos_article_analyse") or "",
            placeholder="Titre / apport direct pour ton projet…",
        )

        st.markdown("**SYSTÈME**")
        col_s1, col_s2 = st.columns(2)
        col_s1.caption(f"Focus total sem. : {readouts['system_focus_txt']}")
        col_s2.caption(f"Écran distractif sem. : {readouts['system_ecran_txt']}")

        st.markdown("**RÉSONNANCE**")
        penta_resonance = st.text_area(
            "RÉSONNANCE — Service / Relations / Mémoire",
            value=d.get("pentagone_resonance") or "",
            height=90,
            placeholder="Service invisible · Temps proches · Gratitude…",
        )

        st.markdown(
            f'<div style="border-left:3px solid {GRAY};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>IV. L'OMBRE (L'Anti-Soi)</strong></div>",
            unsafe_allow_html=True,
        )
        col_o1, col_o2, col_o3 = st.columns(3)
        with col_o1:
            ombre_med = st.text_area(
                "Signal de Médiocrité",
                value=d.get("ombre_mediocrite") or "",
                height=80,
                placeholder="Tâche administrative critique reportée ?",
            )
        with col_o2:
            ombre_cons = st.text_area(
                "Le Consommateur",
                value=d.get("ombre_consommateur") or "",
                height=80,
                placeholder="Temps écran : création ou consommation passive ?",
            )
        with col_o3:
            ombre_men = st.text_area(
                "Le Menteur",
                value=d.get("ombre_menteur") or "",
                height=80,
                placeholder="Ai-je trahi le journal pour masquer une faiblesse ?",
            )

        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["sky_blue"]};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>{get_profile('audit.alignement_titre', 'V. ALIGNEMENT OPÉRATIONNEL')}</strong></div>",
            unsafe_allow_html=True,
        )
        col_al1, col_al2 = st.columns(2)
        with col_al1:
            prerequis = st.text_input(
                get_profile("audit.alignement_label_1", "Statut des prérequis"),
                value=d.get("alignement_prerequis") or "",
            )
        with col_al2:
            stage = st.text_input(
                get_profile("audit.alignement_label_2", "Statut du stage / de la formation"),
                value=d.get("alignement_stage") or "",
            )
        friction_semaine = st.text_area(
            "Point de friction tactique ou physique de la semaine",
            value=d.get("alignement_friction_semaine") or "",
            height=70,
        )

        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>VI. PLAN DE BATAILLE — SEMAINE N+1</strong></div>",
            unsafe_allow_html=True,
        )
        col_bat1, col_bat2 = st.columns(2)
        with col_bat1:
            plan_prio = st.text_area(
                "La Priorité Unique (The One Thing)",
                value=d.get("plan_priorite_unique") or "",
                height=90,
                placeholder="Si je ne fais que ceci, la semaine est une réussite…",
            )
        plan_drill_engagement = d.get("plan_drill_engagement") or ""
        with col_bat2:
            if user_config.engagement_actif():
                plan_drill_engagement = st.text_input(
                    f"{user_config.engagement_libelle()} sanctuarisé(e) (jour & heure)",
                    value=plan_drill_engagement,
                    placeholder="Ex : mardi 18h — séance dédiée…",
                )

        submitted = st.form_submit_button("Sauvegarder l'audit", use_container_width=True)

    if submitted:
        try:
            audits.sauvegarder_audit_hebdo(
                selected_id,
                {
                    "jauge_energie": jauge,
                    "alerte_rouge": alerte,
                    "correction_immediate": correction,
                    "pentagone_resonance": penta_resonance,
                    "ombre_mediocrite": ombre_med,
                    "ombre_consommateur": ombre_cons,
                    "ombre_menteur": ombre_men,
                    "forge_jours_engagement_mois": jours_mois,
                    "jours_engagement_semaine": jours_engagement_sem,
                    "forge_drill_engagement": drill_eng,
                    "forge_hardskills_sujet": hardskills_sujet,
                    "forge_pro_champ_1": pro_champ_1,
                    "forge_pro_champ_2": pro_champ_2,
                    "forge_pro_champ_3": pro_champ_3,
                    "forge_pro_blocage": pro_blocage,
                    "forge_pro_dependance_tiers": pro_dep_tiers,
                    "logos_avancement_uvs": logos_uvs,
                    "logos_projet_tx": logos_tx,
                    "logos_article_analyse": logos_article,
                    "alignement_prerequis": prerequis,
                    "alignement_stage": stage,
                    "alignement_friction_semaine": friction_semaine,
                    "plan_priorite_unique": plan_prio,
                    "plan_drill_engagement": plan_drill_engagement,
                },
                social_val,
            )
            st.session_state.pop(_data_key, None)
            st.session_state.pop(_readouts_key, None)
            st.success("Audit enregistré.")
            st.rerun()
        except Exception as exc:
            st.error(f"Erreur : {exc}")
