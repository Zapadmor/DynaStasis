"""Onglet « Log Workouts » : saisie d'une séance après coup, avec les mêmes règles que la PWA.

Le formulaire construit le même payload que `POST /api/workouts` (validé par `WorkoutIn`) et l'enregistre
par `workout_db.import_session` : volume, coefficients, durée, journal quotidien et numéro d'entraînement
sont donc identiques à ceux d'une séance saisie sur le téléphone."""

from __future__ import annotations

import datetime
import uuid

import streamlit as st
from pydantic import ValidationError

from src.api.schemas import WorkoutIn
from src.app.views.vigueur.historique import _render_history
from src.app.views.vigueur.seance import rendre_elements
from src.collectors import workout_db
from src.core import training_counter
from src.core.tz import today_local
from src.database.connection import db_session
from src.services import workouts as w

WK = "wk"
_META = ("wk_name", "wk_date", "wk_heure", "wk_duree", "wk_poids", "wk_note")
_WIDGETS = (*_META, "wk_tpl", "wk_add", "wk_new_name", "wk_new_kind", "wk_emom_noms", "wk_emom_min")
_KINDS = {
    "Charge (barre, haltères)": "charge",
    "Corps + lest": "corps",
    "Statique (secondes)": "statique",
}
CONFIRM_DELETE = "workout_confirm_delete_id"


# ── état ────────────────────────────────────────────────────────────────────


def _etat_vide() -> dict:
    return {"elements": [], "crees": [], "uid": 0, "template_id": None, "edition_id": None}


def _etat() -> dict:
    if WK not in st.session_state:
        st.session_state[WK] = _etat_vide()
    return st.session_state[WK]


def _element(etat: dict, kind: str, **kw) -> dict:
    etat["uid"] += 1
    return {"uid": etat["uid"], "ver": 0, "kind": kind, **kw}


def _message(kind: str, texte: str) -> None:
    st.session_state["wk_msg"] = (kind, texte)


def _lecture_base() -> tuple[list[dict], dict, float | None]:
    with db_session() as conn:
        return (
            workout_db.get_exercises(),
            workout_db.last_sets_by_exercise(conn),
            workout_db.last_bodyweight(conn),
        )


def _catalogue(exercices: list[dict], etat: dict) -> dict[str, dict]:
    """Exercices proposables : bibliothèque + exercices créés dans cette séance (pas encore enregistrés)."""
    cat = {
        e["name"]: {
            "name": e["name"],
            "create": False,
            "load_formula": e["load_formula"],
            "unit": e["unit"],
            "category": e["category"],
        }
        for e in exercices
    }
    for info in etat["crees"]:
        cat.setdefault(info["name"], info)
    return cat


def _ligne_vide(prev: list[dict] | None = None) -> dict:
    p = prev[0] if prev else None
    return {
        "type": "N",
        "side": p.get("side") if p else None,
        "kg": p["weight_kg"] if p else 0.0,
        "reps": p["reps"] if p else 0.0,
        "rpe": None,
        "minute": None,
        "duree_s": None,
    }


# ── callbacks (exécutés avant le rendu : ils peuvent modifier les clés de widgets) ──


def _reinit() -> None:
    for k in _WIDGETS:
        st.session_state.pop(k, None)
    st.session_state[WK] = _etat_vide()


def _charger_template() -> None:
    tid = st.session_state.get("wk_tpl")
    if tid is None:
        return
    etat = _etat()
    detail = workout_db.get_template_detail(tid)
    etat["elements"], etat["template_id"] = [], tid
    for ex in detail.get("exercises", []):
        info = {
            "name": ex["name"],
            "create": False,
            "load_formula": ex["load_formula"],
            "unit": ex["unit"],
        }
        if ex.get("emom_interval_sec"):
            etat["elements"].append(
                _element(etat, "emom", infos=[info], rows=w.lignes_emom_modele(info, ex["sets"]))
            )
        else:
            etat["elements"].append(
                _element(
                    etat,
                    "exo",
                    info=info,
                    rows=w.lignes_depuis_modele(ex["sets"]) or [_ligne_vide()],
                )
            )
    st.session_state["wk_name"] = f"{detail['name']} — {st.session_state['wk_date']:%d/%m/%Y}"


def _ajouter_exercice() -> None:
    etat = _etat()
    nom = st.session_state.get("wk_add")
    if not nom:
        return
    exercices, precedent, _ = _lecture_base()
    info = _catalogue(exercices, etat)[nom]
    info = {k: info[k] for k in ("name", "create", "load_formula", "unit")}
    etat["elements"].append(
        _element(etat, "exo", info=info, rows=[_ligne_vide(precedent.get(nom))])
    )
    st.session_state["wk_add"] = None


def _creer_exercice() -> None:
    etat = _etat()
    nom = st.session_state.get("wk_new_name", "").strip()
    exercices, precedent, _ = _lecture_base()
    if not nom:
        return _message("err", "Nom d'exercice requis.")
    if nom.lower() in {n.lower() for n in _catalogue(exercices, etat)}:
        return _message("err", "Cet exercice existe déjà : choisis-le dans la liste.")
    genre = _KINDS[st.session_state.get("wk_new_kind", "Charge (barre, haltères)")]
    info = {
        "name": nom,
        "create": True,
        "load_formula": "weight" if genre == "charge" else "bw_plus_weight",
        "unit": "sec" if genre == "statique" else "reps",
    }
    etat["crees"].append(info)
    etat["elements"].append(_element(etat, "exo", info=info, rows=[_ligne_vide()]))
    st.session_state["wk_new_name"] = ""
    return None


def _creer_emom() -> None:
    etat = _etat()
    noms = st.session_state.get("wk_emom_noms", [])
    minutes = int(st.session_state.get("wk_emom_min", 10))
    if not w.duree_emom_valide(len(noms), minutes):
        return _message(
            "err",
            f"{len(noms)} exercice(s) : la durée doit être un multiple de {len(noms) or 'N'} "
            f"(une minute par exercice).",
        )
    exercices, precedent, _ = _lecture_base()
    cat = _catalogue(exercices, etat)
    infos = [{k: cat[n][k] for k in ("name", "create", "load_formula", "unit")} for n in noms]
    etat["elements"].append(
        _element(etat, "emom", infos=infos, rows=w.lignes_emom(infos, minutes, precedent))
    )
    st.session_state["wk_emom_noms"] = []
    return None


def _charger_edition(session_id: int) -> None:
    detail = workout_db.get_session_detail(session_id)
    if not detail:
        return
    f = w.formulaire_depuis_detail(detail)
    _reinit()
    etat = _etat()
    etat["edition_id"], etat["template_id"] = session_id, f["template_id"]
    for el in f["elements"]:
        etat["elements"].append(_element(etat, **el))
        if el["kind"] == "exo":
            etat["crees"].append(el["info"])
    ss = st.session_state
    ss["wk_name"], ss["wk_date"], ss["wk_heure"] = f["name"], f["debut"].date(), f["debut"].time()
    ss["wk_duree"] = int(f["duree_min"] or 0)
    ss["wk_poids"], ss["wk_note"] = float(f["poids_kg"] or 0.0), f["note"]


# ── enregistrement ──────────────────────────────────────────────────────────


@st.dialog("Séance enregistrée")
def _dialogue(info: dict) -> None:
    st.markdown(f"### Entraînement #{info['number']}")
    st.markdown(f"**Volume {info['volume']:,.0f} kg**".replace(",", " "))
    if info.get("duree"):
        st.caption(f"Durée enregistrée : {info['duree']:g} min")
    if info.get("template_id") and st.button(
        "Mettre à jour le template avec ces performances", key="wk_tpl_upd"
    ):
        workout_db.update_template_from_session(info["session_id"])
        st.success("Template mis à jour.")
    if st.button("Fermer", key="wk_dlg_close"):
        st.rerun()


def _enregistrer(etat: dict, elements: list[dict]) -> None:
    ss = st.session_state
    debut = datetime.datetime.combine(ss["wk_date"], ss["wk_heure"])
    payload = w.construire_payload(
        name=ss["wk_name"],
        debut=debut,
        duree_min=ss["wk_duree"] or None,
        poids_kg=ss["wk_poids"] or None,
        template_id=etat["template_id"],
        note=ss.get("wk_note"),
        elements=elements,
        client_uuid=uuid.uuid4().hex,
    )
    if not payload["exercises"]:
        st.error("Aucune série renseignée : saisis au moins des répétitions.")
        return
    try:
        data = WorkoutIn(**payload).model_dump()
    except ValidationError as exc:
        st.error("Séance invalide : " + "; ".join(e["msg"] for e in exc.errors()))
        return
    w.numeroter_series(data)
    with db_session() as conn:
        if etat["edition_id"]:
            session_id = etat["edition_id"]
            workout_db.replace_session(conn, session_id, data)
        else:
            session_id, _ = workout_db.import_session(conn, data)
        numero = training_counter.session_number(conn, session_id)
        row = conn.execute(
            "SELECT session_volume_kg, duration_min, template_id FROM workout_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    ss["wk_saved"] = {
        "session_id": session_id,
        "number": numero,
        "volume": row["session_volume_kg"] or 0,
        "duree": row["duration_min"],
        "template_id": row["template_id"],
    }
    _reinit()
    st.rerun()


# ── onglet ──────────────────────────────────────────────────────────────────


def _tab_log_workouts() -> None:
    etat = _etat()
    ss = st.session_state
    info_enregistree = ss.pop("wk_saved", None)
    if info_enregistree:
        _dialogue(info_enregistree)

    exercices, precedent, poids = _lecture_base()
    today = today_local()
    ss.setdefault("wk_name", f"Séance du {today:%d/%m/%Y}")
    ss.setdefault("wk_date", today)
    ss.setdefault("wk_heure", datetime.time(18, 0))
    ss.setdefault("wk_duree", 60)
    ss.setdefault("wk_poids", float(poids or 0.0))
    ss.setdefault("wk_note", "")

    if ss.get("wk_msg"):
        kind, texte = ss.pop("wk_msg")
        (st.error if kind == "err" else st.info)(texte)

    # ── confirmation de suppression ──
    sessions = workout_db.get_sessions(limit=20)
    finished = [s for s in sessions if s["finished_at"]]
    del_id = ss.get(CONFIRM_DELETE)
    if del_id is not None:
        cible = next((s for s in finished if s["id"] == del_id), None)
        st.warning(
            f"Supprimer la séance du **{cible['date_entry'] if cible else del_id}** ? Irréversible."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Confirmer la suppression", key="workout_del_confirm", type="primary"):
                workout_db.delete_session(del_id)
                ss[CONFIRM_DELETE] = None
                st.rerun()
        with c2:
            if st.button("Annuler", key="workout_del_cancel"):
                ss[CONFIRM_DELETE] = None
                st.rerun()
        st.markdown("---")

    edition = etat["edition_id"]
    st.subheader(
        f"Modifier la séance n°{edition}" if edition else "Nouvelle séance (saisie après coup)"
    )

    c_nom, c_date, c_heure = st.columns([4, 2, 2])
    with c_nom:
        st.text_input("Nom", key="wk_name")
    with c_date:
        st.date_input("Date", key="wk_date")
    with c_heure:
        st.time_input("Heure de début", key="wk_heure", step=300)
    c_duree, c_poids, c_note = st.columns([2, 2, 4])
    with c_duree:
        st.number_input(
            "Durée (min)",
            min_value=0,
            max_value=600,
            step=5,
            key="wk_duree",
            help="Temps d'entraînement enregistré au journal quotidien (0 = non renseigné)",
        )
    with c_poids:
        st.number_input(
            "Poids du corps (kg)", min_value=0.0, max_value=300.0, step=0.5, key="wk_poids"
        )
    with c_note:
        st.text_input("Note", key="wk_note")

    catalogue = _catalogue(exercices, etat)

    # ── template (séance vide seulement) ──
    if not etat["elements"] and not edition:
        modeles = workout_db.get_templates()
        st.selectbox(
            "Template",
            options=[m["id"] for m in modeles],
            format_func=lambda i: next(m["name"] for m in modeles if m["id"] == i),
            index=None,
            placeholder="Partir d'un template (facultatif)",
            key="wk_tpl",
        )
        st.button("Charger le template", on_click=_charger_template, disabled=not modeles)

    # ── exercices saisis ──
    elements = rendre_elements(etat["elements"], precedent)

    # ── ajout d'un exercice / d'un EMOM ──
    with st.expander("Ajouter un exercice", expanded=not etat["elements"]):
        noms = sorted(catalogue, key=lambda n: ((catalogue[n].get("category") or "~"), n.lower()))
        c_sel, c_btn = st.columns([4, 1])
        with c_sel:
            st.selectbox(
                "Exercice",
                options=noms,
                format_func=lambda n: (
                    f"{n}  ({catalogue[n]['category']})" if catalogue[n].get("category") else n
                ),
                index=None,
                placeholder="Choisir un exercice",
                key="wk_add",
                label_visibility="collapsed",
            )
        with c_btn:
            st.button("Ajouter", on_click=_ajouter_exercice, key="wk_add_btn")
        st.markdown("**Nouvel exercice**")
        c_n, c_k, c_c = st.columns([3, 3, 1])
        with c_n:
            st.text_input(
                "Nom",
                key="wk_new_name",
                label_visibility="collapsed",
                placeholder="Nom du nouvel exercice",
            )
        with c_k:
            st.selectbox("Type", list(_KINDS), key="wk_new_kind", label_visibility="collapsed")
        with c_c:
            st.button("Créer", on_click=_creer_exercice, key="wk_new_btn")
    with st.expander("Nouvel EMOM (exercices à tour de rôle)"):
        st.multiselect("Exercices dans l'ordre (un par minute)", noms, key="wk_emom_noms")
        st.number_input(
            "Durée totale (min)", min_value=1, max_value=120, value=10, step=1, key="wk_emom_min"
        )
        st.caption("La durée doit être un multiple du nombre d'exercices.")
        st.button("Créer l'EMOM", on_click=_creer_emom, key="wk_emom_btn")

    # ── enregistrer ──
    st.markdown("---")
    c_ok, c_ann = st.columns([3, 1])
    with c_ok:
        if st.button(
            "Enregistrer les modifications" if edition else "Enregistrer la séance",
            type="primary",
            key="wk_save",
            disabled=not elements,
        ):
            _enregistrer(etat, elements)
    with c_ann:
        st.button("Annuler", on_click=_reinit, key="wk_cancel")

    if finished:
        st.markdown("---")
        _render_history(finished, _charger_edition, CONFIRM_DELETE)
