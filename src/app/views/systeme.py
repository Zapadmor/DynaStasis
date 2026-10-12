from __future__ import annotations

import contextlib
import datetime
import io
import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

from src.app.components import PALETTE
from src.database.connection import db_session

_PILIERS_OPTIONS = ["VIGUEUR", "LOGOS", "FORGE", "RÉSONANCE", "FINANCE"]

_ROOT = Path(__file__).resolve().parents[3]

_TABLES = [
    "semaines_audit",
    "audit_narrative",
    "habitude_logs",
    "focus_sessions",
    "vigueur_entries",
    "screen_sessions",
    "transactions",
    "soldes_comptes",
    "comptes",
    "objectifs",
    "taches",
    "cours_ecole",
    "logos_gpa",
    "logs_systeme",
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _run_cmd(cmd: str) -> tuple[bool, str]:
    """Appel en sous-processus — conservé pour finance et init-db."""
    try:
        result = subprocess.run(
            [sys.executable, str(_ROOT / "main.py"), cmd],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_ROOT),
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output or f"Commande `{cmd}` terminée."
    except subprocess.TimeoutExpired:
        return False, f"Timeout — `{cmd}` dépasse 2 minutes."
    except Exception as exc:
        return False, str(exc)


def _run_vigueur_direct() -> tuple[bool, str]:
    """Appel en-process de vigueur_bot.run() — instantané, même env Python."""
    buf = io.StringIO()
    try:
        sys.path.insert(0, str(_ROOT)) if str(_ROOT) not in sys.path else None
        from bots.vigueur_bot import run as _vbot_run  # noqa: PLC0415

        with contextlib.redirect_stdout(buf):
            _vbot_run()
        return True, buf.getvalue().strip() or "Sync Vigueur terminé."
    except Exception as exc:
        out = buf.getvalue().strip()
        return False, f"{out}\nErreur : {exc}".strip()


def _run_logos_direct() -> tuple[bool, str]:
    """Appel en-process de logos_bot.run() — même env Python que l'app."""
    buf = io.StringIO()
    try:
        sys.path.insert(0, str(_ROOT)) if str(_ROOT) not in sys.path else None
        from bots.logos_bot import run as _lbot_run  # noqa: PLC0415

        with contextlib.redirect_stdout(buf):
            _lbot_run()
        return True, buf.getvalue().strip() or "Sync Logos terminé."
    except Exception as exc:
        out = buf.getvalue().strip()
        return False, f"{out}\nErreur : {exc}".strip()


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION : PAUSE SYSTÈME
# ─────────────────────────────────────────────────────────────────────────────


def _update_frozen_weeks(conn, date_debut: str, date_fin: str, frozen: int) -> None:
    """Marque/démarque les semaines_audit dont la semaine (lun→dim) chevauche la plage donnée."""
    conn.execute(
        "UPDATE semaines_audit SET is_frozen = ?"
        " WHERE week_start <= ? AND date(week_start, '+6 days') >= ?",
        (frozen, date_fin, date_debut),
    )


def _render_freeze_manager() -> None:
    today = datetime.date.today()

    with db_session() as conn:
        active = conn.execute(
            "SELECT * FROM system_freezes WHERE statut = 'actif' ORDER BY date_debut DESC LIMIT 1"
        ).fetchone()
        history = conn.execute(
            "SELECT * FROM system_freezes ORDER BY created_at DESC LIMIT 20"
        ).fetchall()

    # ── Bannière statut actuel ───────────────────────────────────────────────
    if active:
        d_fin = datetime.date.fromisoformat(active["date_fin"])
        restant = (d_fin - today).days
        piliers_list = json.loads(active["piliers"] or "[]")
        piliers_str = " · ".join(piliers_list) if piliers_list else "—"

        if restant < 0:
            badge_color = PALETTE["tiger"]
            badge_label = f"Dépassée de {-restant} jour(s) — pensez à clore !"
        else:
            badge_color = PALETTE["amber"]
            badge_label = f"{restant} jour(s) restant(s)"

        st.markdown(
            f'<div style="background:{badge_color}22;border-left:4px solid {badge_color};'
            f'padding:14px 18px;border-radius:6px;margin-bottom:16px;">'
            f'<strong style="color:{badge_color};font-size:1.05rem;">SYSTÈME EN PAUSE</strong><br>'
            f'<span style="opacity:.9;">{active["raison"]}</span><br>'
            f'<small style="opacity:.7;">{active["date_debut"]} → {active["date_fin"]}'
            f" &nbsp;·&nbsp; {badge_label}</small><br>"
            f'<small style="opacity:.7;">Piliers développés : {piliers_str}</small>'
            f"</div>",
            unsafe_allow_html=True,
        )
        col_end, _ = st.columns([1, 3])
        with col_end:
            if st.button("Terminer la pause", key="end_freeze", type="primary"):
                # Ne dégèle que la portion non vécue de la pause : les semaines
                # déjà passées sous pause (date_debut → aujourd'hui) restent
                # gelées, même si la pause est close avant sa date de fin prévue.
                real_end = min(today.isoformat(), active["date_fin"])
                with db_session() as conn:
                    conn.execute(
                        "UPDATE system_freezes SET statut = 'termine' WHERE id = ?",
                        (active["id"],),
                    )
                    conn.execute(
                        "UPDATE semaines_audit SET is_frozen = 0"
                        " WHERE week_start <= ? AND date(week_start, '+6 days') >= ?"
                        " AND NOT (week_start <= ? AND date(week_start, '+6 days') >= ?)",
                        (active["date_fin"], active["date_debut"], real_end, active["date_debut"]),
                    )
                st.success("Pause terminée — suivi rétabli pour les semaines à venir.")
                st.rerun()
    else:
        st.info("Aucune pause active — le système tourne normalement.", icon="✅")

    st.markdown("---")

    # ── Formulaire de création ───────────────────────────────────────────────
    st.markdown(
        f'<div style="border-left:3px solid {PALETTE["amber"]};padding:6px 12px;margin-bottom:12px;">'
        f"<strong>Planifier une pause</strong><br>"
        f'<span style="font-size:.8rem;opacity:.7;">'
        f"Les semaines couvertes seront marquées comme gelées (is_frozen) et exclues des moyennes"
        f"</span></div>",
        unsafe_allow_html=True,
    )

    with st.form("freeze_form"):
        col_d, col_f = st.columns(2)
        with col_d:
            date_debut = st.date_input("Date de début", value=today, key="freeze_debut")
        with col_f:
            date_fin = st.date_input(
                "Date de fin",
                value=today + datetime.timedelta(weeks=2),
                key="freeze_fin",
            )

        raison = st.text_area(
            "Raison",
            placeholder="Ex : Randonnée sans accès PC, toutes les habitudes suspendues sauf VIGUEUR",
            height=80,
            key="freeze_raison",
        )
        piliers = st.multiselect(
            "Piliers développés pendant cette période",
            options=_PILIERS_OPTIONS,
            help="Les piliers que tu continues à travailler en dehors du système",
            key="freeze_piliers",
        )
        contexte = st.text_area(
            "Contexte / Intentions",
            placeholder="Pourquoi ce break est légitime, ce que tu espères en tirer, objectifs connexes…",
            height=90,
            key="freeze_contexte",
        )

        submitted = st.form_submit_button("Activer la pause", type="primary")
        if submitted:
            if not raison.strip():
                st.error("La raison est obligatoire.")
            elif date_fin < date_debut:
                st.error("La date de fin doit être après la date de début.")
            else:
                n_days = (date_fin - date_debut).days + 1
                n_weeks = max(1, round(n_days / 7))
                with db_session() as conn:
                    conn.execute(
                        "INSERT INTO system_freezes"
                        " (date_debut, date_fin, raison, piliers, contexte)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (
                            date_debut.isoformat(),
                            date_fin.isoformat(),
                            raison.strip(),
                            json.dumps(piliers),
                            contexte.strip() or None,
                        ),
                    )
                    _update_frozen_weeks(conn, date_debut.isoformat(), date_fin.isoformat(), 1)
                st.success(
                    f"Pause activée du {date_debut} au {date_fin} "
                    f"(~{n_weeks} semaine(s) exclues du suivi)."
                )
                st.rerun()

    # ── Historique ───────────────────────────────────────────────────────────
    if history:
        st.markdown("---")
        st.markdown("### Historique des pauses")
        for row in history:
            piliers_h = json.loads(row["piliers"] or "[]")
            label_statut = "ACTIF" if row["statut"] == "actif" else "terminé"
            color_statut = PALETTE["amber"] if row["statut"] == "actif" else PALETTE["sky_blue"]
            with st.expander(f"{row['date_debut']} → {row['date_fin']}  ·  {row['raison'][:55]}"):
                st.markdown(
                    f'<span style="color:{color_statut};font-weight:600;">{label_statut}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Raison :** {row['raison']}")
                if piliers_h:
                    st.markdown(f"**Piliers développés :** {' · '.join(piliers_h)}")
                if row["contexte"]:
                    st.markdown(f"**Contexte :** {row['contexte']}")
                st.caption(f"Créé le {row['created_at']}")

    _render_manual_week_override()


def _render_manual_week_override() -> None:
    """Bascule manuellement le statut gelé d'une semaine précise.

    Filet de sécurité quand le rapprochement automatique (date_debut/date_fin
    de la pause vs week_start) rate une semaine à cause d'un décalage de label.
    """
    st.markdown("---")
    st.markdown("### Correction manuelle d'une semaine")
    st.caption(
        "À utiliser si une semaine n'a pas été marquée gelée correctement "
        "(décalage de label, semaine créée après coup, etc.)."
    )

    with db_session() as conn:
        weeks = conn.execute(
            "SELECT id, week_label, week_start, is_frozen FROM semaines_audit"
            " ORDER BY week_start DESC LIMIT 20"
        ).fetchall()
    if not weeks:
        st.info("Aucune semaine enregistrée.")
        return

    week_map = {f"{w['week_label']} — {'Gelée' if w['is_frozen'] else 'Active'}": w for w in weeks}
    choice = st.selectbox("Semaine", list(week_map.keys()), key="manual_freeze_week_select")
    selected = week_map[choice]

    col_toggle, col_save = st.columns([3, 1])
    with col_toggle:
        new_frozen = st.checkbox(
            "Marquer cette semaine comme gelée (exclue des calculs)",
            value=bool(selected["is_frozen"]),
            key=f"manual_freeze_toggle_{selected['id']}",
        )
    with col_save:
        if st.button("Enregistrer", key="manual_freeze_save", use_container_width=True):
            with db_session() as conn:
                conn.execute(
                    "UPDATE semaines_audit SET is_frozen = ? WHERE id = ?",
                    (int(new_frozen), selected["id"]),
                )
            st.success(f"Semaine « {selected['week_label']} » mise à jour.")
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION : SYNCHRONISATION
# ─────────────────────────────────────────────────────────────────────────────


_STATUT_LIBELLES = {
    "ok": "OK",
    "erreur": "Erreur",
    "delai": "Délai dépassé",
    "non_configure": "Non configurée",
}


def _render_sync_status() -> None:
    """État par source (dernière réussite, dernière erreur, durée) + synchronisation globale."""
    st.markdown("### État des sources")
    from src.core.sync_runner import default_sources, exit_code, run_all  # noqa: PLC0415

    with db_session() as conn:
        rows = {}
        if _table_exists(conn, "sync_checkpoints"):
            cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_checkpoints)")}
            if "statut" in cols:
                rows = {
                    r["source"]: dict(r) for r in conn.execute("SELECT * FROM sync_checkpoints")
                }

    table = []
    for src in default_sources():
        r = rows.get(src.key, {})
        table.append(
            {
                "Source": src.key,
                "Statut": _STATUT_LIBELLES.get(r.get("statut"), "Jamais lancée"),
                "Dernière réussite": r.get("last_success_at") or "—",
                "Dernière erreur": (
                    f"{r['last_error_at']} — {(r.get('last_error') or '')[-120:]}"
                    if r.get("last_error_at")
                    else "—"
                ),
                "Durée (s)": r.get("last_duration_s"),
            }
        )
    st.dataframe(table, use_container_width=True, hide_index=True)

    if st.button("Synchroniser toutes les sources configurées", key="sync_all"):
        with st.spinner("Synchronisation en cours (chaque source est isolée)…"):
            results = run_all()
        actives = [r for r in results if r.status != "non_configure"]
        if not actives:
            st.info("Aucune source configurée : rien à synchroniser (voir docs/configuration.md).")
        elif exit_code(results):
            st.error(
                "Échec : "
                + ", ".join(
                    f"{r.key} ({_STATUT_LIBELLES.get(r.status, r.status)})"
                    for r in actives
                    if r.failed
                )
            )
        else:
            st.success(f"{len(actives)} source(s) synchronisée(s).")
    st.markdown("---")


def _render_sync() -> None:
    _render_sync_status()
    st.markdown("### Synchronisation des données")

    col_v, col_l, col_f = st.columns(3, gap="large")

    with col_v:
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["blue_green"]};padding:6px 12px;">'
            f"<strong>Vigueur</strong><br>"
            f'<span style="font-size:.8rem;opacity:.7;">Intervals.icu → vigueur_entries</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")
        if st.button("Sync Vigueur", key="sync_vigueur", use_container_width=True):
            with st.spinner("Synchronisation Intervals.icu…"):
                ok, msg = _run_vigueur_direct()
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

        st.link_button(
            "Sync Suunto sur intervals.icu",
            url="https://intervals.icu",
            use_container_width=True,
            help="Ouvre intervals.icu — clique sur le bouton sync Suunto, attends 30-60 s, puis reviens appuyer sur 'Sync Vigueur'.",
        )

    with col_l:
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};padding:6px 12px;">'
            f"<strong>Temps d'écran</strong><br>"
            f'<span style="font-size:.8rem;opacity:.7;">Samsung ADB → screen_sessions</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")
        if st.button("Sync Écran", key="sync_logos", use_container_width=True):
            with st.spinner("Synchronisation ADB…"):
                ok, msg = _run_logos_direct()
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    with col_f:
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["sky_blue"]};padding:6px 12px;">'
            f"<strong>Finance</strong><br>"
            f'<span style="font-size:.8rem;opacity:.7;">CSV inbox → transactions / soldes</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")
        if st.button("Sync Finance", key="sync_finance", use_container_width=True):
            with st.spinner("Import CSV finances…"):
                ok, msg = _run_cmd("finance")
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    st.markdown("---")
    col_score, col_init = st.columns(2, gap="large")

    with col_score:
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["sky_blue"]};padding:6px 12px;">'
            f"<strong>Scores hebdo</strong><br>"
            f'<span style="font-size:.8rem;opacity:.7;">Recalcule le score 0-100 et le pentagone médian</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")
        if st.button("Recalculer les scores", key="recalc_scores", use_container_width=True):
            with st.spinner("Recalcul en cours…"):
                from src.database.connection import db_session as _db
                from src.services.semaines import trigger_cascade_week

                with _db() as conn:
                    week_ids = [
                        r["semaine_id"]
                        for r in conn.execute(
                            "SELECT DISTINCT semaine_id FROM habitude_logs WHERE semaine_id IS NOT NULL"
                        ).fetchall()
                    ]
                for wid in week_ids:
                    trigger_cascade_week(wid)
            st.success(f"{len(week_ids)} semaines recalculées — pentagone actualisé.")

    with col_init:
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};padding:6px 12px;">'
            f"<strong>Base de données</strong><br>"
            f'<span style="font-size:.8rem;opacity:.7;">Initialise le schéma et applique les migrations</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")
        if st.button("Initialiser / Migrer la base", key="init_db", use_container_width=True):
            with st.spinner("Initialisation SQLite…"):
                ok, msg = _run_cmd("init-db")
            (st.success if ok else st.error)(msg)

    st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION : GESTION DES THÈMES
# ─────────────────────────────────────────────────────────────────────────────


def _render_theme_manager() -> None:
    from src.app import theme as _theme

    current = _theme.current_theme_name()
    colors = _theme._load()

    # ── Thème actif ──────────────────────────────────────────────────────────
    st.markdown("### Thème actif")

    col_info, col_sw = st.columns([3, 2])
    with col_info:
        st.markdown(f"**`{current}`**")
        st.caption(
            "Les couleurs sont appliquées au redémarrage de l'app (Streamlit relit config.toml)."
        )
    with col_sw:
        st.markdown(_theme.color_swatches_html(colors), unsafe_allow_html=True)
        st.caption("Primaire · Fond · Fond sec. · Texte")

    st.markdown("")
    col_rand, col_del = st.columns(2)
    with col_rand:
        if st.button("Rotation aléatoire", key="rotate_theme_mgr", use_container_width=True):
            import random

            all_t = _theme.list_themes()
            available = [t for t in all_t if t != current] or all_t
            chosen = random.choice(available)
            try:
                _theme.apply_theme(chosen)
                st.success(f"Thème **{chosen}** appliqué — rechargez la page.")
            except Exception as exc:
                st.error(str(exc))

    with col_del:
        if st.button("Supprimer ce thème", key="del_theme_open", use_container_width=True):
            st.session_state["_confirm_del_theme"] = True

    if st.session_state.get("_confirm_del_theme"):
        st.warning(
            f"Supprimer définitivement **{current}** du repo ?\n\n"
            "Un autre thème sera automatiquement sélectionné."
        )
        cc, cd = st.columns(2)
        with cc:
            if st.button("Confirmer la suppression", key="del_theme_confirm", type="primary"):
                try:
                    _theme.delete_theme(current)
                    new_current = _theme.current_theme_name()
                    st.session_state.pop("_confirm_del_theme", None)
                    st.success(
                        f"Thème **{current}** supprimé. "
                        f"Nouveau thème actif : **{new_current}** — rechargez la page."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with cd:
            if st.button("Annuler", key="del_theme_cancel"):
                st.session_state.pop("_confirm_del_theme", None)
                st.rerun()

    st.markdown("---")

    # ── Appliquer un thème existant ──────────────────────────────────────────
    st.markdown("### Thèmes disponibles")

    all_themes = _theme.list_themes()
    default_idx = all_themes.index(current) if current in all_themes else 0
    sel = st.selectbox(
        "Choisir un thème",
        all_themes,
        index=default_idx,
        key="apply_theme_sel",
    )
    sel_colors = _theme._load_by_name(sel)
    st.markdown(_theme.color_swatches_html(sel_colors), unsafe_allow_html=True)
    st.caption("Primaire · Fond · Fond sec. · Texte")
    st.markdown("")
    if st.button("Appliquer ce thème", key="apply_theme_btn"):
        try:
            _theme.apply_theme(sel)
            st.success(f"Thème **{sel}** appliqué — rechargez la page.")
        except Exception as exc:
            st.error(str(exc))

    st.markdown("---")

    # ── Créer un nouveau thème ────────────────────────────────────────────────
    st.markdown("### Créer un nouveau thème")

    with st.expander("+ Nouveau thème depuis des couleurs", expanded=False):
        theme_name = st.text_input(
            "Nom du thème",
            placeholder="mon_theme_sombre",
            key="new_theme_name",
        )
        col_p, col_b = st.columns(2)
        with col_p:
            new_primary = st.color_picker("Couleur primaire", "#ffb703", key="new_theme_primary")
        with col_b:
            new_bg = st.color_picker("Fond principal", "#023047", key="new_theme_bg")
        col_sb, col_t = st.columns(2)
        with col_sb:
            new_sbg = st.color_picker("Fond secondaire", "#012535", key="new_theme_sbg")
        with col_t:
            new_text = st.color_picker("Texte", "#8ecae6", key="new_theme_text")

        preview_colors = {
            "primaryColor": new_primary,
            "backgroundColor": new_bg,
            "secondaryBackgroundColor": new_sbg,
            "textColor": new_text,
        }
        st.markdown("**Aperçu :**")
        st.markdown(_theme.color_swatches_html(preview_colors), unsafe_allow_html=True)
        st.caption("Primaire · Fond · Fond sec. · Texte")

        st.markdown("")
        col_save, col_apply = st.columns(2)
        with col_save:
            if st.button("Créer le thème", key="create_theme_btn"):
                if not theme_name.strip():
                    st.error("Donnez un nom au thème.")
                else:
                    try:
                        safe = _theme.create_theme(theme_name, preview_colors)
                        st.success(f"Thème **{safe}** créé — visible dans la liste ci-dessus.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        with col_apply:
            if st.button("Créer et appliquer", key="create_apply_theme_btn"):
                if not theme_name.strip():
                    st.error("Donnez un nom au thème.")
                else:
                    try:
                        safe = _theme.create_theme(theme_name, preview_colors)
                        _theme.apply_theme(safe)
                        st.success(f"Thème **{safe}** créé et appliqué — rechargez la page.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION : ÉTAT DE LA BASE
# ─────────────────────────────────────────────────────────────────────────────


def _render_db_status() -> None:
    st.markdown("### État de la base de données")

    with db_session() as conn:
        rows_info = []
        for table in _TABLES:
            if _table_exists(conn, table):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                rows_info.append({"Table": table, "Lignes": count, "Statut": "OK"})
            else:
                rows_info.append({"Table": table, "Lignes": "—", "Statut": "MANQUANTE"})

    try:
        import pandas as pd

        df = pd.DataFrame(rows_info)
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception:
        for r in rows_info:
            icon = "" if r["Statut"] == "OK" else "!"
            st.text(f"{icon} {r['Table']:<30} {str(r['Lignes']):>6}  {r['Statut']}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION : LOGS SYSTÈME
# ─────────────────────────────────────────────────────────────────────────────


def _render_logs() -> None:
    st.markdown("### Logs des synchronisations")

    with db_session() as conn:
        if not _table_exists(conn, "logs_systeme"):
            st.caption("Table `logs_systeme` non encore créée.")
            return
        rows = conn.execute("""
            SELECT timestamp, type_sync, source, statut, message
            FROM logs_systeme ORDER BY timestamp DESC LIMIT 20
        """).fetchall()

    if not rows:
        st.caption("Aucun log système enregistré.")
        return

    try:
        import pandas as pd

        df = pd.DataFrame([dict(r) for r in rows]).rename(
            columns={
                "timestamp": "Horodatage",
                "type_sync": "Type",
                "source": "Source",
                "statut": "Statut",
                "message": "Message",
            }
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception:
        for r in rows:
            st.text(f"{r['timestamp']} [{r['type_sync']}] {r['statut']} — {r['message'] or ''}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION : REQUÊTE SQL LIBRE
# ─────────────────────────────────────────────────────────────────────────────


def _render_query_tool() -> None:
    st.markdown("### Requête SQL de débogage")
    st.caption("Accès direct en lecture à la base SQLite locale. SELECT uniquement.")

    query = st.text_area(
        "Requête SQL",
        value="SELECT * FROM semaines_audit ORDER BY week_start DESC LIMIT 5",
        height=80,
        key="sql_query",
    )

    if st.button("Exécuter", key="run_query"):
        q = query.strip()
        # Refuser les requêtes non-SELECT pour protéger la base
        if not q.upper().startswith("SELECT"):
            st.error("Seules les requêtes SELECT sont autorisées dans cet outil.")
        else:
            try:
                with db_session() as conn:
                    rows = conn.execute(q).fetchall()
                if rows:
                    import pandas as pd

                    st.dataframe(
                        pd.DataFrame([dict(r) for r in rows]),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(f"{len(rows)} ligne(s) retournée(s).")
                else:
                    st.info("Aucun résultat.")
            except Exception as exc:
                st.error(f"Erreur SQL : {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render() -> None:
    st.header("SYSTEME — Synchronisation & Débogage")

    tab_pause, tab_sync, tab_themes, tab_db, tab_logs, tab_sql = st.tabs(
        ["Pause", "Synchronisation", "Thèmes", "Base de données", "Logs", "SQL"]
    )

    with tab_pause:
        _render_freeze_manager()

    with tab_sync:
        _render_sync()

    with tab_themes:
        _render_theme_manager()

    with tab_db:
        _render_db_status()

    with tab_logs:
        _render_logs()

    with tab_sql:
        _render_query_tool()
