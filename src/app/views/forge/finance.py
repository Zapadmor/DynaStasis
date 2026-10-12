"""Onglet « Finance »."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.app.components import PALETTE
from src.core.tz import today_local
from src.services import finance

# ── Finance ───────────────────────────────────────────────────────────────────

_BUDGET_FILE = Path(__file__).resolve().parents[4] / "data" / "budget.yaml"

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
# ONGLET FINANCE
# ─────────────────────────────────────────────────────────────────────────────


def _tab_finance() -> None:
    st.markdown("### Finance & Souveraineté Économique")

    mois = today_local().strftime("%Y-%m")

    # ── 1. Treemap + Suivi investissements ────────────────────────────────────
    col_tree, col_invest = st.columns([2, 1], gap="large")

    with col_tree:
        st.markdown("#### Patrimoine")
        try:
            from src.collectors.finance_viz import _build_treemap

            soldes = finance.soldes_par_enveloppe()
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
        invest = finance.verifier_versements(mois)

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
                finance.enregistrer_versements(
                    today_local().isoformat(), pea_check, av_fe_check, av_uc_check
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
    finance.assurer_comptes()
    comptes = finance.comptes()

    with st.expander("Soldes comptes — mise à jour", expanded=False):
        st.caption("Saisissez les soldes actuels de chaque compte, puis enregistrez.")
        date_snap = st.date_input(
            "Date du relevé", value=today_local(), key="pat_date_snap"
        ).isoformat()

        for c in comptes:
            sk = f"solde_{c['id']}"
            if sk not in st.session_state:
                st.session_state[sk] = finance.solde_actuel(c["id"]) or 0.0

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
                finance.enregistrer_solde(c["id"], val, date_snap)
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
                    balances = finance.parser_revolut_csv(content)
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
                            "Date du relevé", value=today_local(), key="rev_date"
                        ).isoformat()
                        if st.button("Importer ces soldes", key="rev_import"):
                            n = 0
                            for prod, bal in balances.items():
                                tc = _product_to_tc.get(prod, prod.lower())
                                compte = rev_comptes.get(tc)
                                if compte:
                                    finance.enregistrer_solde(compte["id"], bal, date_rev)
                                    n += 1
                            st.success(f"{n} comptes Revolut mis à jour.")
                            st.rerun()
                except Exception as e:
                    st.error(f"Erreur de parsing Revolut : {e}")

            else:  # Linxea XLSX
                try:
                    content_bytes = uploaded.read()
                    lignes = finance.parser_linxea_xlsx(content_bytes)
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
                            "Date du relevé", value=today_local(), key="lx_date"
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
                                    finance.enregistrer_position(
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
                                    total = finance.total_positions(compte["id"], date_lx)
                                    if total > 0:
                                        finance.enregistrer_solde(
                                            compte["id"], float(total), date_lx
                                        )
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
            positions = finance.positions_compte(compte_pos["id"])

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
                        value=today_local().isoformat(),
                        placeholder="AAAA-MM-JJ",
                    )
                if st.form_submit_button("Enregistrer la position") and pos_support.strip():
                    snap = pos_date.strip() or today_local().isoformat()
                    finance.enregistrer_position(
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
                    total_pos = finance.total_positions(compte_pos["id"], snap)
                    finance.enregistrer_solde(compte_pos["id"], float(total_pos), snap)
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
