"""Éditeur de séance a posteriori : une carte par exercice (tableau de séries) ou par EMOM."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services import workouts as w

_TYPES = list(w.TYPES_SERIE)
_COTES = ["–", "D", "G"]


def _prec_txt(p: dict | None, unit: str) -> str:
    if not p:
        return ""
    val = f"{p['weight_kg']:g}×{p['reps']:g}{'s' if unit == 'sec' else ''}"
    if p.get("side"):
        val += f" {p['side']}"
    if p.get("duration_s"):
        val += f" · {p['duration_s']:g}s"
    return val


def _libelles(info: dict) -> tuple[str, str]:
    """(libellé de la colonne charge, libellé de la colonne répétitions) selon le type d'exercice."""
    charge = "Lest (kg)" if info.get("load_formula") == "bw_plus_weight" else "Kg"
    reps = "Sec" if info.get("unit") == "sec" else "Reps"
    return charge, reps


def _config(info: dict) -> dict:
    charge, reps = _libelles(info)
    sec = info.get("unit") == "sec"
    return {
        "Type": st.column_config.SelectboxColumn(
            "Type", options=_TYPES, default="N", width="small"
        ),
        "Côté": st.column_config.SelectboxColumn(
            "Côté", options=_COTES, default="–", width="small"
        ),
        "Kg": st.column_config.NumberColumn(
            charge, min_value=0.0, step=0.5, format="%g", default=0.0
        ),
        "Reps": st.column_config.NumberColumn(
            reps, min_value=0.0, step=0.01 if sec else 1.0, format="%g", default=0.0
        ),
        "RPE": st.column_config.NumberColumn(
            "RPE", min_value=1.0, max_value=10.0, step=0.5, format="%g"
        ),
        "Préc.": st.column_config.TextColumn("Préc.", disabled=True),
    }


def _rows_depuis_df(df: pd.DataFrame, *, emom: bool) -> list[dict]:
    rows = []
    for rec in df.to_dict("records"):
        row = {
            "type": rec.get("Type") or "N",
            "side": None if rec.get("Côté") in (None, "", "–") else rec["Côté"],
            "kg": rec.get("Kg"),
            "reps": rec.get("Reps"),
            "rpe": rec.get("RPE"),
            "minute": None,
            "duree_s": None,
        }
        if emom:
            row["minute"] = rec.get("Min")
            row["exercice"] = rec.get("Exercice")
            row["duree_s"] = rec.get("Temps (s)")
        rows.append(row)
    return rows


def _df_exo(el: dict, precedent: dict[str, list[dict]]) -> pd.DataFrame:
    prev = precedent.get(el["info"]["name"], [])
    unit = el["info"].get("unit", "reps")
    data = [
        {
            "Type": r["type"],
            "Côté": r["side"] or "–",
            "Kg": r["kg"],
            "Reps": r["reps"],
            "RPE": r["rpe"],
            "Préc.": _prec_txt(prev[i] if i < len(prev) else None, unit),
        }
        for i, r in enumerate(el["rows"])
    ]
    df = pd.DataFrame(data, columns=["Type", "Côté", "Kg", "Reps", "RPE", "Préc."])
    return df.astype({"Kg": "float64", "Reps": "float64", "RPE": "float64"})


def _df_emom(el: dict, precedent: dict[str, list[dict]]) -> pd.DataFrame:
    data = [
        {
            "Min": int(r["minute"]),
            "Exercice": r["exercice"],
            "Kg": r["kg"],
            "Reps": r["reps"],
            "RPE": r["rpe"],
            "Temps (s)": r["duree_s"],
        }
        for r in el["rows"]
    ]
    df = pd.DataFrame(data, columns=["Min", "Exercice", "Kg", "Reps", "RPE", "Temps (s)"])
    return df.astype({"Kg": "float64", "Reps": "float64", "RPE": "float64", "Temps (s)": "float64"})


def _carte_exo(el: dict, precedent: dict[str, list[dict]]) -> list[dict]:
    info = el["info"]
    cle = f"wk_ed_{el['uid']}_{el['ver']}"
    c_titre, c_prec, c_vide, c_sup = st.columns([4, 3, 3, 2])
    with c_titre:
        st.markdown(f"**{info['name']}**")
    edited = st.data_editor(
        _df_exo(el, precedent),
        key=cle,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config=_config(info),
    )
    rows = _rows_depuis_df(edited, emom=False)
    if info.get("load_formula") == "bw_plus_weight":
        st.caption("Lest en plus du poids du corps.")
    return _actions(el, rows, precedent, (c_prec, c_vide, c_sup))


def _carte_emom(el: dict, precedent: dict[str, list[dict]]) -> list[dict]:
    noms = " / ".join(i["name"] for i in el["infos"])
    c_titre, c_vide, c_sup = st.columns([5, 4, 2])
    with c_titre:
        st.markdown(f"**EMOM** — {noms} · {len(el['rows'])} min")
    cfg = {
        "Min": st.column_config.NumberColumn("Min", disabled=True, width="small"),
        "Exercice": st.column_config.TextColumn("Exercice", disabled=True),
        "Kg": st.column_config.NumberColumn("Kg / lest", min_value=0.0, step=0.5, format="%g"),
        "Reps": st.column_config.NumberColumn("Reps / sec", min_value=0.0, step=1.0, format="%g"),
        "RPE": st.column_config.NumberColumn(
            "RPE", min_value=1.0, max_value=10.0, step=0.5, format="%g"
        ),
        "Temps (s)": st.column_config.NumberColumn(
            "Temps (s)",
            min_value=0.0,
            max_value=60.0,
            step=0.5,
            format="%g",
            help="Temps mis pour faire les répétitions dans la minute",
        ),
    }
    edited = st.data_editor(
        _df_emom(el, precedent),
        key=f"wk_ed_{el['uid']}_{el['ver']}",
        num_rows="fixed",
        hide_index=True,
        use_container_width=True,
        column_config=cfg,
    )
    rows = _rows_depuis_df(edited, emom=True)
    return _actions(el, rows, precedent, (None, c_vide, c_sup))


def _actions(el: dict, rows: list[dict], precedent: dict, cols: tuple) -> list[dict]:
    """Boutons d'une carte : copier le précédent, retirer les séries vides, supprimer."""
    c_prec, c_vide, c_sup = cols
    nb_vides = sum(1 for r in rows if w.ligne_vide(r))
    if c_prec is not None and el["kind"] == "exo":
        prev = precedent.get(el["info"]["name"])
        with c_prec:
            if st.button("Copier le précédent", key=f"wk_prev_{el['uid']}", disabled=not prev):
                el["rows"] = [
                    {"type": "N", "side": p.get("side"), "kg": p["weight_kg"], "reps": p["reps"],
                     "rpe": None, "minute": None, "duree_s": None}
                    for p in prev
                ]  # fmt: skip
                el["ver"] += 1
                st.rerun()
    with c_vide:
        if st.button(
            f"Retirer les séries vides ({nb_vides})",
            key=f"wk_vide_{el['uid']}",
            disabled=not nb_vides,
        ):
            el["rows"] = w.retirer_lignes_vides(rows)
            el["ver"] += 1
            if not el["rows"]:
                st.session_state["wk"]["elements"].remove(el)
            st.rerun()
    with c_sup:
        if st.button("Suppr", key=f"wk_sup_{el['uid']}", help="Supprimer cet exercice"):
            st.session_state["wk"]["elements"].remove(el)
            st.rerun()
    return rows


def rendre_elements(elements: list[dict], precedent: dict[str, list[dict]]) -> list[dict]:
    """Affiche les cartes ; retourne les éléments avec leurs lignes telles qu'éditées à l'écran."""
    resultat = []
    for el in list(elements):
        with st.container(border=True):
            rows = _carte_exo(el, precedent) if el["kind"] == "exo" else _carte_emom(el, precedent)
        resultat.append({**el, "rows": rows})
    return resultat
