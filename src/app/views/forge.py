from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.app.components import PALETTE
from src.app.theme import contrast_text as _contrast_text
from src.core import projets
from src.core.tz import today_paris
from src.database.connection import db_session

_ROOT = Path(__file__).resolve().parents[3]
_BUDGET_FILE = _ROOT / "data" / "budget.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS FINANCE
# ─────────────────────────────────────────────────────────────────────────────


def _soldes_from_db() -> dict:
    """Construit le dict soldes attendu par _build_treemap depuis v_net_worth_actuel."""
    s = {
        k: 0.0
        for k in [
            "cmb_cheques",
            "cmb_lj",
            "cmb_lep",
            "rev_cheques",
            "rev_epargne",
            "rev_pocket",
            "fortuneo_pea",
            "linxea_uc",
            "linxea_fe",
        ]
    }
    try:
        with db_session() as conn:
            rows = conn.execute(
                """SELECT c.source, c.type_compte, c.classe_actif, sc.solde
                   FROM soldes_comptes sc JOIN comptes c ON sc.compte_id=c.id
                   WHERE sc.date_snapshot=(
                       SELECT MAX(date_snapshot) FROM soldes_comptes s2 WHERE s2.compte_id=sc.compte_id
                   ) AND c.actif=1"""
            ).fetchall()
        for r in rows:
            src = (r["source"] or "").lower()
            tc = (r["type_compte"] or "").lower()
            ca = r["classe_actif"] or ""
            v = float(r["solde"] or 0.0)
            if "cmb" in src:
                if "courant" in tc:
                    s["cmb_cheques"] += v
                elif "lep" in tc:
                    s["cmb_lep"] += v
                else:
                    s["cmb_lj"] += v
            elif "revolut" in src:
                if any(k in tc for k in ("epargne", "coffre", "vault")):
                    s["rev_epargne"] += v
                elif "pocket" in tc:
                    s["rev_pocket"] += v
                else:
                    s["rev_cheques"] += v
            elif "fortuneo" in src:
                s["fortuneo_pea"] += v  # especes_pea + pea → enveloppe PEA
            elif "linxea" in src:
                if ca == "fonds_euros":
                    s["linxea_fe"] += v
                else:
                    s["linxea_uc"] += v
    except Exception:
        pass
    return s


def _check_invest_mois(mois: str) -> dict:
    """Vérifie si PEA et AV ont été versés ce mois depuis semaines_audit + transactions."""
    r = {
        "pea": False,
        "av_fe": False,
        "av_uc": False,
        "pea_montant": 0.0,
        "av_montant": 0.0,
        "source": "—",
    }
    try:
        with db_session() as conn:
            # Source 1 — flags manuels dans semaines_audit
            flags = conn.execute(
                """SELECT SUM(investissement_pea) pea,
                          SUM(av_fonds_euros)     av_fe,
                          SUM(av_uc_diversifies)  av_uc
                   FROM semaines_audit WHERE week_start LIKE ?""",
                (f"{mois}%",),
            ).fetchone()
            if flags and any([flags["pea"], flags["av_fe"], flags["av_uc"]]):
                r.update(
                    {
                        "pea": bool(flags["pea"]),
                        "av_fe": bool(flags["av_fe"]),
                        "av_uc": bool(flags["av_uc"]),
                        "source": "semaines_audit",
                    }
                )

            # Source 2 — transactions catégorisées épargne/investissement
            txs = conn.execute(
                """SELECT libelle, montant FROM transactions
                   WHERE date_op LIKE ? AND categorie='epargne_investissement'""",
                (f"{mois}%",),
            ).fetchall()
            for tx in txs:
                lib = (tx["libelle"] or "").upper()
                m = abs(float(tx["montant"] or 0.0))
                if any(k in lib for k in ("FORTUNEO", "PEA", "ETF", "ISHARES")):
                    r["pea"] = True
                    r["pea_montant"] += m
                    r["source"] = "transactions"
                if any(k in lib for k in ("LINXEA", "SURAVENIR", "ASSURANCE VIE")):
                    r["av_fe"] = True
                    r["av_montant"] += m
                    r["source"] = "transactions"
    except Exception:
        pass
    return r


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS PATRIMOINE MANUEL
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_COMPTES = [
    ("cmb", "courant", "CMB Compte Chèques", "liquidites"),
    ("cmb", "livret_jeune", "CMB Livret Jeune", "livrets"),
    ("cmb", "lep", "CMB LEP", "livrets"),
    ("fortuneo", "especes_pea", "Fortuneo PEA — Espèces", "liquidites"),
    ("fortuneo", "pea", "Fortuneo PEA — ETF", "actions"),
    ("revolut", "courant", "Revolut Current", "liquidites"),
    ("revolut", "epargne", "Revolut Épargne", "livrets"),
    ("revolut", "pocket", "Revolut Pockets", "liquidites"),
    ("linxea", "fonds_euros", "Linxea AV — Fonds Euros", "fonds_euros"),
    ("linxea", "uc_diversifies", "Linxea AV — UC Diversifiés", "actions"),
]


def _ensure_comptes() -> None:
    """Crée les comptes par défaut si la table est vide."""
    try:
        with db_session() as conn:
            count = conn.execute("SELECT COUNT(*) FROM comptes").fetchone()[0]
            if count == 0:
                conn.executemany(
                    "INSERT INTO comptes (source, type_compte, libelle, classe_actif) VALUES (?,?,?,?)",
                    _DEFAULT_COMPTES,
                )
    except Exception:
        pass


def _load_comptes() -> list[dict]:
    """Charge les comptes actifs, dédupliqués par (source, type_compte).

    Pour chaque paire (source, type_compte), garde le compte avec la donnée
    la plus récente ; en l'absence de donnée, garde le premier id.
    """
    try:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT c.id, c.source, c.type_compte, c.libelle, c.classe_actif, "
                "MAX(sc.date_snapshot) AS last_snap "
                "FROM comptes c "
                "LEFT JOIN soldes_comptes sc ON sc.compte_id = c.id "
                "WHERE c.actif = 1 "
                "GROUP BY c.id "
                "ORDER BY c.source, c.type_compte, last_snap DESC"
            ).fetchall()
        seen: set[tuple] = set()
        unique: list[dict] = []
        for r in rows:
            key = (r["source"], r["type_compte"])
            if key not in seen:
                seen.add(key)
                unique.append(dict(r))
        unique.sort(key=lambda c: (c["classe_actif"], c["source"], c["type_compte"]))
        return unique
    except Exception:
        return []


def _get_solde_actuel(compte_id: int) -> float | None:
    """Retourne le dernier solde connu pour un compte."""
    try:
        with db_session() as conn:
            row = conn.execute(
                "SELECT solde FROM soldes_comptes WHERE compte_id=? ORDER BY date_snapshot DESC LIMIT 1",
                (compte_id,),
            ).fetchone()
        return float(row["solde"]) if row else None
    except Exception:
        return None


def _upsert_solde(compte_id: int, solde: float, date_snapshot: str) -> None:
    """Insère ou met à jour le solde d'un compte à une date donnée."""
    with db_session() as conn:
        conn.execute(
            """INSERT INTO soldes_comptes (compte_id, date_snapshot, solde)
               VALUES (?, ?, ?)
               ON CONFLICT(compte_id, date_snapshot) DO UPDATE SET solde=excluded.solde""",
            (compte_id, date_snapshot, solde),
        )


def _load_positions_compte(compte_id: int) -> list[dict]:
    """Charge les dernières positions pour un compte d'investissement."""
    try:
        with db_session() as conn:
            rows = conn.execute(
                """SELECT * FROM positions_investissement
                   WHERE compte_id=? AND date_snapshot=(
                       SELECT MAX(date_snapshot) FROM positions_investissement p2
                       WHERE p2.compte_id=?
                   )
                   ORDER BY support""",
                (compte_id, compte_id),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _upsert_position(
    date_snapshot: str,
    compte_id: int,
    support: str,
    nb_parts: float | None,
    cotation: float | None,
    valeur: float,
    plus_value: float | None,
    perf_ytd: str | None,
    categorie: str | None,
    frais_pct: float | None = None,
) -> None:
    with db_session() as conn:
        conn.execute(
            """INSERT INTO positions_investissement
               (date_snapshot, compte_id, support, nb_parts, cotation, valeur,
                plus_value, perf_ytd, categorie, frais_pct)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(date_snapshot, compte_id, support) DO UPDATE SET
                   nb_parts=excluded.nb_parts, cotation=excluded.cotation,
                   valeur=excluded.valeur, plus_value=excluded.plus_value,
                   perf_ytd=excluded.perf_ytd, categorie=excluded.categorie,
                   frais_pct=excluded.frais_pct""",
            (
                date_snapshot,
                compte_id,
                support,
                nb_parts,
                cotation,
                valeur,
                plus_value,
                perf_ytd,
                categorie,
                frais_pct,
            ),
        )


def _parse_revolut_csv(content: str) -> dict[str, float]:
    """Parse CSV Revolut et retourne {produit: solde_final}."""
    import csv
    import io

    reader = csv.DictReader(io.StringIO(content))
    balances: dict[str, tuple[float, str]] = {}
    for row in reader:
        if row.get("State") != "COMPLETED":
            continue
        if row.get("Currency", "EUR") != "EUR":
            continue
        product = row.get("Product", "Current")
        try:
            balance = float(row["Balance"])
            completed = row.get("Completed Date", "")[:10]
        except (ValueError, KeyError):
            continue
        existing = balances.get(product)
        if existing is None or completed >= existing[1]:
            balances[product] = (balance, completed)
    return {prod: bal for prod, (bal, _) in balances.items()}


def _parse_linxea_xlsx(content: bytes) -> list[dict]:
    """Parse XLSX Linxea et retourne les lignes de positions."""
    try:
        import io

        import openpyxl
    except ImportError:
        return []

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    lignes = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not any(row):
            continue
        try:
            categorie = str(row[5] or "")
            support = str(row[7] or "")
            nb_parts = float(row[9] or 0)
            cotation = float(row[10] or 0)
            valeur = float(row[12] or 0)
            pv = float(row[13] or 0)
            perf_ytd = str(row[15] or "")
            if not support or valeur == 0:
                continue
            lignes.append(
                {
                    "categorie": categorie,
                    "support": support,
                    "nb_parts": nb_parts,
                    "cotation": cotation,
                    "valeur": valeur,
                    "plus_value": pv,
                    "perf_ytd": perf_ytd,
                }
            )
        except (ValueError, TypeError, IndexError):
            continue
    return lignes


# ─────────────────────────────────────────────────────────────────────────────
# DONNÉES STATIQUES
# ─────────────────────────────────────────────────────────────────────────────

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


# ── Finance ───────────────────────────────────────────────────────────────────

_REVENUS = [
    {"Source": "Salaire net", "Montant (€)": 1109.64},
    {"Source": "APL", "Montant (€)": 178.00},
    {"Source": "Prime d'activité", "Montant (€)": 201.51},
    {"Source": "Action logement", "Montant (€)": 100.00},
    {"Source": "Tickets Resto", "Montant (€)": 189.00},
]

_BUDGET = [
    {"Catégorie": "Logement", "Montant (€)": 400.00, "% Revenus": "22.5%", "Détail": ""},
    {"Catégorie": "Vie Quotidienne", "Montant (€)": 400.00, "% Revenus": "22.5%", "Détail": ""},
    {"Catégorie": "Abonnements", "Montant (€)": 46.05, "% Revenus": "2.6%", "Détail": ""},
    {"Catégorie": "Transports", "Montant (€)": 100.00, "% Revenus": "5.6%", "Détail": ""},
    {
        "Catégorie": "Investissements",
        "Montant (€)": 832.10,
        "% Revenus": "46.8%",
        "Détail": "582.40€ ETF Monde Fortuneo + 249.70€ Linxea Suravenir 2",
    },
]

_MATELAS = [
    {
        "Compte": "CMB Livret Jeune",
        "Solde (€)": 1_600,
        "Note": "946€ (1 mois dépenses) + 654€ surplus",
    },
    {
        "Compte": "LEP",
        "Solde (€)": 4_400.99,
        "Note": "~2 mois de dépenses courantes + Dernier recours",
    },
]

_DEADLINES = [
    {"Date": "01/03/2026", "Objectif": "Matelas 6 000 € FU validé", "Statut": "ACCOMPLI"},
    {
        "Date": "01/03/2027",
        "Objectif": "Budget Iron-man 1 500 € (vélo 1 000€ + équip. 500€)",
        "Statut": "À VENIR",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS OBJECTIFS — CRUD SQLite
# ─────────────────────────────────────────────────────────────────────────────


def _load_objectifs() -> tuple[list[dict], str | None]:
    try:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT * FROM objectifs WHERE statut != 'abandonne' ORDER BY priorite, created_at"
            ).fetchall()
            return [dict(r) for r in rows], None
    except Exception as e:
        return [], str(e)


def _load_taches(objectif_id: int) -> list[dict]:
    try:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT * FROM taches WHERE objectif_id=? AND statut != 'annule' ORDER BY priorite, created_at",
                (objectif_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _create_objectif(
    titre: str, pilier: str, date_cible: str | None, description: str, priorite: int
) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT INTO objectifs (titre, pilier, date_cible, description, priorite) VALUES (?,?,?,?,?)",
            (titre, pilier, date_cible or None, description or None, priorite),
        )


def _archive_objectif(objectif_id: int) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE objectifs SET statut='abandonne', updated_at=datetime('now') WHERE id=?",
            (objectif_id,),
        )


def _create_tache(objectif_id: int, titre: str, priorite: int, date_echeance: str | None) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT INTO taches (titre, objectif_id, priorite, date_echeance) VALUES (?,?,?,?)",
            (titre, objectif_id, priorite, date_echeance or None),
        )


def _toggle_tache(tache_id: int, done: bool) -> None:
    with db_session() as conn:
        if done:
            conn.execute(
                "UPDATE taches SET statut='fait', completed_at=datetime('now') WHERE id=?",
                (tache_id,),
            )
        else:
            conn.execute(
                "UPDATE taches SET statut='todo', completed_at=NULL WHERE id=?",
                (tache_id,),
            )


def _delete_tache(tache_id: int) -> None:
    with db_session() as conn:
        conn.execute("UPDATE taches SET statut='annule' WHERE id=?", (tache_id,))


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


# ─────────────────────────────────────────────────────────────────────────────
# ONGLET FINANCE
# ─────────────────────────────────────────────────────────────────────────────


def _tab_finance() -> None:
    st.markdown("### Finance & Souveraineté Économique")

    mois = today_paris().strftime("%Y-%m")

    # ── 1. Treemap + Suivi investissements ────────────────────────────────────
    col_tree, col_invest = st.columns([2, 1], gap="large")

    with col_tree:
        st.markdown("#### Patrimoine")
        try:
            from src.collectors.finance_viz import _build_treemap

            soldes = _soldes_from_db()
            net_worth = sum(soldes.values())
            if net_worth > 0:
                st.plotly_chart(_build_treemap(soldes), use_container_width=True)
                st.caption(
                    f"Net Worth total : **{net_worth:,.2f} €** — source : v_net_worth_actuel"
                )
            else:
                st.info(
                    "Aucune donnée patrimoniale. Mettez à jour vos soldes via le formulaire ci-dessous."
                )
        except Exception as e:
            st.warning(f"Treemap indisponible : {e}")

    with col_invest:
        st.markdown("#### Virements du mois")
        invest = _check_invest_mois(mois)

        try:
            import yaml

            budget = (
                yaml.safe_load(_BUDGET_FILE.read_text(encoding="utf-8"))
                if _BUDGET_FILE.exists()
                else {}
            )
        except Exception:
            budget = {}

        invest_postes = budget.get("depenses", {}).get("investissements", {}).get("postes", [])
        suivi = [p for p in invest_postes if p.get("suivi_mensuel")]

        if not suivi:
            st.caption("Aucun poste suivi_mensuel défini dans budget.yaml.")
        else:
            for p in suivi:
                nom = p["nom"]
                montant_cible = p["montant"]
                is_pea = "PEA" in nom.upper() or "FORTUNEO" in nom.upper()
                is_av = "AV" in nom.upper() or "LINXEA" in nom.upper()
                done = (invest["pea"] and is_pea) or (invest["av_fe"] and is_av)
                montant_reel = invest["pea_montant"] if is_pea else invest["av_montant"]
                color = PALETTE["blue_green"] if done else PALETTE["amber"]
                icon = "✓" if done else "⚠"
                detail = p.get("detail", "")
                montant_str = (
                    f"{montant_reel:,.0f} € / {montant_cible:,.0f} €"
                    if done and montant_reel
                    else f"Cible : {montant_cible:,.0f} €"
                )
                st.markdown(
                    f'<div style="border-left:3px solid {color};padding:8px 14px;'
                    f'margin-bottom:10px;border-radius:0 8px 8px 0;">'
                    f'<span style="color:{color};font-weight:700;">{icon}</span> '
                    f'<strong style="font-size:.9rem;">{nom}</strong><br>'
                    f'<span style="font-size:.8rem;opacity:.75;">{montant_str}</span><br>'
                    f'<span style="font-size:.75rem;opacity:.55;">{detail}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

        if invest["source"] != "—":
            st.caption(f"Source : {invest['source']} — {mois}")

        st.markdown("")
        # Flags manuels semaines_audit (mise à jour directe)
        with st.expander("Marquer manuellement", expanded=False):
            st.caption("Cochez après avoir effectué le virement. Met à jour semaines_audit.")
            pea_check = st.checkbox("PEA Fortuneo versé", value=invest["pea"], key="inv_pea_manual")
            av_fe_check = st.checkbox(
                "AV Linxea — Fonds euros versé", value=invest["av_fe"], key="inv_av_fe_manual"
            )
            av_uc_check = st.checkbox(
                "AV Linxea — UC diversifiés versé", value=invest["av_uc"], key="inv_av_uc_manual"
            )
            if st.button("Enregistrer", key="inv_save"):
                from src.core.system_engine import get_or_create_week_id

                week_id = get_or_create_week_id(today_paris().isoformat())
                with db_session() as conn:
                    conn.execute(
                        """UPDATE semaines_audit
                           SET investissement_pea=?, av_fonds_euros=?, av_uc_diversifies=?,
                               updated_at=datetime('now')
                           WHERE id=?""",
                        (int(pea_check), int(av_fe_check), int(av_uc_check), week_id),
                    )
                st.success("Enregistré.")
                st.rerun()

    st.markdown("---")

    # ── 2. Sankey mensuel ─────────────────────────────────────────────────────
    st.markdown("#### Flux budgétaire mensuel")
    try:
        import yaml

        from src.collectors.finance_viz import _build_sankey

        if _BUDGET_FILE.exists():
            budget = yaml.safe_load(_BUDGET_FILE.read_text(encoding="utf-8")) or {}
            st.plotly_chart(_build_sankey(budget), use_container_width=True)
            st.caption("Budget théorique — modifier via `data/budget.yaml`")
        else:
            st.info("data/budget.yaml introuvable.")
    except Exception as e:
        st.warning(f"Sankey indisponible : {e}")

    st.markdown("---")

    # ── 3. Mise à jour manuelle du patrimoine ─────────────────────────────────
    _ensure_comptes()
    comptes = _load_comptes()

    with st.expander("Soldes comptes — mise à jour", expanded=False):
        st.caption("Saisissez les soldes actuels de chaque compte, puis enregistrez.")
        date_snap = st.date_input(
            "Date du relevé", value=today_paris(), key="pat_date_snap"
        ).isoformat()

        for c in comptes:
            sk = f"solde_{c['id']}"
            if sk not in st.session_state:
                st.session_state[sk] = _get_solde_actuel(c["id"]) or 0.0

        cols_per_row = 3
        for i in range(0, len(comptes), cols_per_row):
            batch = comptes[i : i + cols_per_row]
            cols = st.columns(len(batch))
            for j, c in enumerate(batch):
                with cols[j]:
                    st.number_input(
                        c["libelle"],
                        min_value=0.0,
                        step=1.0,
                        format="%.2f",
                        key=f"solde_{c['id']}",
                        help=f"{c['source']} · {c['type_compte']} · {c['classe_actif']}",
                    )

        if st.button("Enregistrer tous les soldes", key="pat_save_soldes"):
            for c in comptes:
                val = float(st.session_state.get(f"solde_{c['id']}", 0.0))
                _upsert_solde(c["id"], val, date_snap)
            st.success(f"Soldes enregistrés pour le {date_snap}.")
            st.rerun()

    with st.expander("Import automatique — Revolut CSV ou Linxea XLSX", expanded=False):
        st.caption(
            "Importez un export CSV Revolut ou XLSX Linxea pour pré-remplir les soldes automatiquement."
        )
        src_import = st.selectbox("Source", ["Revolut (CSV)", "Linxea (XLSX)"], key="import_src")
        uploaded = st.file_uploader("Fichier", type=["csv", "xlsx"], key="import_file")

        if uploaded is not None:
            if "Revolut" in src_import:
                try:
                    content = uploaded.read().decode("utf-8", errors="replace")
                    balances = _parse_revolut_csv(content)
                    if not balances:
                        st.warning("Aucun solde trouvé dans ce fichier Revolut.")
                    else:
                        import pandas as pd

                        _product_to_tc = {
                            "Current": "courant",
                            "Deposit": "epargne",
                            "Savings": "pocket",
                        }
                        rev_comptes = {
                            c["type_compte"]: c for c in comptes if c["source"] == "revolut"
                        }
                        preview_rows = [
                            {
                                "Produit": prod,
                                "Compte": rev_comptes.get(
                                    _product_to_tc.get(prod, prod.lower()), {}
                                ).get("libelle", "Non mappé"),
                                "Solde (€)": round(bal, 2),
                            }
                            for prod, bal in balances.items()
                        ]
                        st.dataframe(
                            pd.DataFrame(preview_rows),
                            hide_index=True,
                            use_container_width=True,
                        )
                        date_rev = st.date_input(
                            "Date du relevé", value=today_paris(), key="rev_date"
                        ).isoformat()
                        if st.button("Importer ces soldes", key="rev_import"):
                            n = 0
                            for prod, bal in balances.items():
                                tc = _product_to_tc.get(prod, prod.lower())
                                compte = rev_comptes.get(tc)
                                if compte:
                                    _upsert_solde(compte["id"], bal, date_rev)
                                    n += 1
                            st.success(f"{n} comptes Revolut mis à jour.")
                            st.rerun()
                except Exception as e:
                    st.error(f"Erreur de parsing Revolut : {e}")

            else:  # Linxea XLSX
                try:
                    content_bytes = uploaded.read()
                    lignes = _parse_linxea_xlsx(content_bytes)
                    if not lignes:
                        st.warning("Aucune position trouvée. Vérifiez le format XLSX Linxea.")
                    else:
                        import pandas as pd

                        df_lx = pd.DataFrame(
                            [
                                {
                                    "Support": lg["support"],
                                    "Parts": round(lg["nb_parts"], 4),
                                    "Cotation (€)": round(lg["cotation"], 4),
                                    "Valeur (€)": round(lg["valeur"], 2),
                                    "PV (€)": round(lg["plus_value"], 2),
                                    "Perf YTD": lg["perf_ytd"],
                                }
                                for lg in lignes
                            ]
                        )
                        st.dataframe(df_lx, hide_index=True, use_container_width=True)
                        st.metric("Total AV", f"{sum(lg['valeur'] for lg in lignes):,.2f} €")
                        date_lx = st.date_input(
                            "Date du relevé", value=today_paris(), key="lx_date"
                        ).isoformat()
                        lx_comptes = {
                            c["type_compte"]: c for c in comptes if c["source"] == "linxea"
                        }
                        if st.button("Importer positions & soldes", key="lx_import"):
                            for ligne in lignes:
                                is_fe = "euro" in ligne.get("categorie", "").lower()
                                tc = "fonds_euros" if is_fe else "uc_diversifies"
                                compte = lx_comptes.get(tc)
                                if compte:
                                    _upsert_position(
                                        date_lx,
                                        compte["id"],
                                        ligne["support"],
                                        ligne["nb_parts"],
                                        ligne["cotation"],
                                        ligne["valeur"],
                                        ligne["plus_value"],
                                        ligne["perf_ytd"],
                                        ligne["categorie"],
                                    )
                            for tc in ("fonds_euros", "uc_diversifies"):
                                compte = lx_comptes.get(tc)
                                if compte:
                                    with db_session() as conn:
                                        total = conn.execute(
                                            "SELECT COALESCE(SUM(valeur),0) FROM positions_investissement "
                                            "WHERE compte_id=? AND date_snapshot=?",
                                            (compte["id"], date_lx),
                                        ).fetchone()[0]
                                    if total > 0:
                                        _upsert_solde(compte["id"], float(total), date_lx)
                            st.success(f"{len(lignes)} positions Linxea importées.")
                            st.rerun()
                except Exception as e:
                    st.error(f"Erreur de parsing Linxea : {e}")

    with st.expander("Positions ETF / Actions (PEA & AV)", expanded=False):
        # Tous les comptes fortuneo/linxea — pas de filtre sur type_compte pour plus de robustesse
        invest_comptes = [c for c in comptes if c["source"] in ("fortuneo", "linxea")]
        if not invest_comptes:
            st.info(
                "Aucun compte Fortuneo ou Linxea trouvé. "
                "Initialisez la base via le formulaire « Soldes comptes »."
            )
        else:
            compte_pos = st.selectbox(
                "Compte",
                invest_comptes,
                format_func=lambda c: c["libelle"],
                key="pos_compte_sel",
            )
            positions = _load_positions_compte(compte_pos["id"])

            if positions:
                import pandas as pd

                df_pos = pd.DataFrame(
                    [
                        {
                            "Support": p["support"],
                            "Nb lots": p["nb_parts"] or 0,
                            "Cotation (€)": p["cotation"] or 0,
                            "Valeur (€)": p["valeur"],
                            "PV (€)": p["plus_value"] or 0,
                            "Frais (%)": p.get("frais_pct") or "",
                            "Perf YTD": p["perf_ytd"] or "",
                        }
                        for p in positions
                    ]
                )
                st.dataframe(df_pos, hide_index=True, use_container_width=True)
                st.caption(
                    f"Total : **{sum(p['valeur'] for p in positions):,.2f} €** "
                    f"· snapshot {positions[0]['date_snapshot']}"
                )
            else:
                st.caption("Aucune position — remplissez le formulaire ci-dessous.")

            st.markdown("**Ajouter / mettre à jour une ligne :**")
            with st.form("form_position", clear_on_submit=True):
                c_sup, c_cat = st.columns([3, 1])
                with c_sup:
                    pos_support = st.text_input(
                        "Support (ETF / Fonds / Action)",
                        placeholder="iShares Core MSCI World ETF USD (Acc)",
                    )
                with c_cat:
                    pos_categorie = st.text_input("Catégorie", placeholder="UC / FE / Action")
                c_parts, c_cot, c_val = st.columns(3)
                with c_parts:
                    pos_parts = st.number_input(
                        "Nb lots / parts", value=0.0, step=0.001, format="%.3f", min_value=0.0
                    )
                with c_cot:
                    pos_cotation = st.number_input(
                        "Cotation (€)", value=0.0, step=0.01, format="%.4f", min_value=0.0
                    )
                with c_val:
                    pos_valeur = st.number_input(
                        "Valeur totale (€)", value=0.0, step=1.0, format="%.2f", min_value=0.0
                    )
                c_pv, c_frais, c_perf, c_date = st.columns(4)
                with c_pv:
                    pos_pv = st.number_input("Plus-value (€)", value=0.0, step=1.0, format="%.2f")
                with c_frais:
                    pos_frais = st.number_input(
                        "Frais annuels (%)", value=0.0, step=0.01, format="%.2f", min_value=0.0
                    )
                with c_perf:
                    pos_perf = st.text_input("Perf YTD", placeholder="+5.3%")
                with c_date:
                    pos_date = st.text_input(
                        "Date snapshot",
                        value=today_paris().isoformat(),
                        placeholder="AAAA-MM-JJ",
                    )
                if st.form_submit_button("Enregistrer la position") and pos_support.strip():
                    snap = pos_date.strip() or today_paris().isoformat()
                    _upsert_position(
                        snap,
                        compte_pos["id"],
                        pos_support.strip(),
                        pos_parts or None,
                        pos_cotation or None,
                        pos_valeur,
                        pos_pv or None,
                        pos_perf.strip() or None,
                        pos_categorie.strip() or None,
                        pos_frais or None,
                    )
                    with db_session() as conn:
                        total_pos = conn.execute(
                            "SELECT COALESCE(SUM(valeur),0) FROM positions_investissement "
                            "WHERE compte_id=? AND date_snapshot=?",
                            (compte_pos["id"], snap),
                        ).fetchone()[0]
                    _upsert_solde(compte_pos["id"], float(total_pos), snap)
                    st.success(
                        f"Position « {pos_support.strip()} » enregistrée — "
                        f"total {float(total_pos):,.2f} €"
                    )
                    st.rerun()

    st.markdown("---")

    # ── 4. Matelas + Deadlines ────────────────────────────────────────────────
    st.info(
        "**Analyse stratégique (Conseil Alexandre) :**  \n"
        "Matelas de sécurité à doubler à 6 000 €. ETF CAC à capitalisation. "
        "Répartition 50/50 fonds euros / UC diversifiés sur AV Linxea Suravenir 2.",
        icon=None,
    )

    col_m, col_d = st.columns([1.2, 1], gap="large")
    with col_m:
        st.markdown("#### Matelas de sécurité — Objectif 6 000 €")
        try:
            import pandas as pd

            df_mat = pd.DataFrame(_MATELAS)
            total_mat = df_mat["Solde (€)"].sum()
            df_mat.loc[len(df_mat)] = {"Compte": "**TOTAL**", "Solde (€)": total_mat, "Note": ""}
            st.dataframe(df_mat, use_container_width=True, hide_index=True)
        except Exception:
            for r in _MATELAS:
                st.text(f"{r['Compte']:<25} {r['Solde (€)']:>6} €")
        total_mat = sum(r["Solde (€)"] for r in _MATELAS)
        pct = min(total_mat / 6000 * 100, 100)
        st.metric("Progression matelas", f"{total_mat:,.0f} € / 6 000 €", delta=f"{pct:.0f}%")
        st.progress(int(pct))

    with col_d:
        st.markdown("#### Deadlines budgétaires")
        for d in _DEADLINES:
            color = PALETTE["blue_green"] if d["Statut"] == "ACCOMPLI" else PALETTE["amber"]
            st.markdown(
                f'<div style="border-left:3px solid {color};padding:6px 14px;margin-bottom:8px;">'
                f"<strong>{d['Date']}</strong><br>{d['Objectif']}<br>"
                f'<span style="font-size:.8rem;color:{color};">{d["Statut"]}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )


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
                _create_objectif(
                    obj_titre.strip(),
                    obj_pilier,
                    obj_date.strip() or None,
                    obj_desc,
                    obj_priorite,
                )
                st.rerun()

    st.markdown("")

    objectifs, err = _load_objectifs()
    if err:
        st.error(f"Erreur DB : {err}")
        st.caption("Cliquez sur 🔄 Synchroniser pour appliquer les migrations manquantes.")
        return
    if not objectifs:
        st.info("Aucun objectif actif. Créez-en un ci-dessus.")
        return

    for obj in objectifs:
        taches = _load_taches(obj["id"])
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
                _archive_objectif(obj["id"])
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
                    _toggle_tache(tache["id"], new_val)
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
                    _delete_tache(tache["id"])
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
                    _create_tache(obj["id"], t_titre.strip(), t_prio, t_date.strip() or None)
                    st.rerun()

        st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render(current_week: dict | None) -> None:
    st.header("FORGE — Projets & Engagement")

    tab_obj, tab_fin, tab_proj = st.tabs(["Objectifs", "Finance", "Projets en cours"])

    with tab_obj:
        _tab_objectifs()

    with tab_fin:
        _tab_finance()

    with tab_proj:
        _tab_projets()
