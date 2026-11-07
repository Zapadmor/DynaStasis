"""Séances d'entraînement : logique pure de la saisie a posteriori (sans Streamlit, testable).

Une séance saisie est une liste ordonnée d'« éléments » :
  - {"kind": "exo",  "info": {name, create, load_formula, unit}, "rows": [ligne, ...]}
  - {"kind": "emom", "infos": [info, ...], "rows": [ligne, ...]}   (exercices à tour de rôle, 1 minute chacun)
Une ligne : {type, side, kg, reps, rpe, minute, duree_s, exercice}. Dans un EMOM, `exercice` nomme l'exercice
de la ligne. `reps` vaut des secondes (décimales admises) pour un exercice statique.
"""

from __future__ import annotations

from datetime import datetime, timedelta

TYPES_SERIE = ("N", "W", "D", "F")


def numeroter_series(payload: dict) -> None:
    """'N' (série de travail) devient '1', '2', … par exercice ; W, F, D inchangés."""
    for ex in payload["exercises"]:
        n = 0
        for s in ex["sets"]:
            if s["set_type"] == "N":
                n += 1
                s["set_type"] = str(n)


def _num(v) -> float | None:
    """Nombre ou None (None, chaîne vide et NaN pandas deviennent None)."""
    if v is None or v == "" or v != v:
        return None
    return float(v)


def ligne_vide(row: dict) -> bool:
    """Une série sans répétitions (ou sans secondes) est vide : elle n'est pas enregistrée."""
    reps = _num(row.get("reps"))
    return reps is None or reps == 0


def retirer_lignes_vides(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not ligne_vide(r)]


def duree_emom_valide(nb_exercices: int, minutes: int) -> bool:
    """La durée totale d'un EMOM doit être un multiple du nombre d'exercices (une minute chacun)."""
    return nb_exercices > 0 and minutes >= nb_exercices and minutes % nb_exercices == 0


def lignes_emom(infos: list[dict], minutes: int, precedent: dict[str, list[dict]]) -> list[dict]:
    """Lignes d'un EMOM : exercices à tour de rôle, minute 1…`minutes`. Valeurs préremplies depuis la
    séance précédente de chaque exercice (dernière série si elle en a moins)."""
    n = len(infos)
    rows = []
    for minute in range(1, minutes + 1):
        info = infos[(minute - 1) % n]
        tour = (minute - 1) // n
        prev = precedent.get(info["name"]) or []
        p = prev[tour] if tour < len(prev) else (prev[-1] if prev else None)
        rows.append(
            {
                "minute": minute,
                "exercice": info["name"],
                "type": "N",
                "side": None,
                "kg": p["weight_kg"] if p else 0.0,
                "reps": p["reps"] if p else 0.0,
                "rpe": None,
                "duree_s": None,
            }
        )
    return rows


def lignes_emom_modele(info: dict, sets: list[dict]) -> list[dict]:
    """Lignes d'un EMOM d'un seul exercice issu d'un template : une série par minute."""
    return [
        {**ligne, "minute": i, "exercice": info["name"]}
        for i, ligne in enumerate(lignes_depuis_modele(sets), start=1)
    ]


def _type_depuis_base(set_type: str) -> str:
    return set_type if set_type in ("W", "F", "D") else "N"


def lignes_depuis_modele(sets: list[dict]) -> list[dict]:
    """Lignes préremplies depuis les séries prévues d'un template (types '1','2'… → 'N')."""
    return [
        {
            "type": _type_depuis_base(s["set_type"]),
            "side": None,
            "kg": float(s["weight_kg"]),
            "reps": float(s["reps"]),
            "rpe": None,
            "minute": None,
            "duree_s": None,
        }
        for s in sets
    ]


def _series(rows: list[dict], *, emom: bool) -> list[dict]:
    out = []
    for r in retirer_lignes_vides(rows):
        minute = _num(r.get("minute")) if emom else None
        out.append(
            {
                "set_type": r.get("type") or "N",
                "weight_kg": _num(r.get("kg")) or 0.0,
                "reps": _num(r["reps"]),
                "rpe": _num(r.get("rpe")),
                "side": r.get("side") or None,
                "completed": True,
                "duration_s": _num(r.get("duree_s")),
                "emom_minute": int(minute) if minute else None,
            }
        )
    return out


def _exercice(info: dict, sets: list[dict], emom: bool) -> dict:
    return {
        "name": info["name"],
        "create": bool(info.get("create")),
        "load_formula": info.get("load_formula") or "weight",
        "unit": info.get("unit") or "reps",
        "emom_interval_sec": 60 if emom else None,
        "sets": sets,
    }


def construire_payload(
    *,
    name: str,
    debut: datetime,
    duree_min: float | None,
    poids_kg: float | None,
    template_id: int | None,
    note: str | None,
    elements: list[dict],
    client_uuid: str,
) -> dict:
    """Payload identique à celui de `POST /api/workouts` (même validation, même `import_session`).

    Les séries vides sont ignorées, un exercice sans série disparaît. La durée (minutes) donne les bornes
    `worked_from` / `worked_to`, d'où le temps d'entraînement enregistré au journal quotidien.
    Les séries de travail gardent le type 'N' : l'appelant valide (`WorkoutIn`) puis appelle
    `numeroter_series`, comme l'API."""
    exercices: list[dict] = []
    for el in elements:
        if el["kind"] == "exo":
            sets = _series(el["rows"], emom=False)
            if sets:
                exercices.append(_exercice(el["info"], sets, emom=False))
        else:
            for info in el["infos"]:
                rows = [r for r in el["rows"] if r.get("exercice") == info["name"]]
                sets = _series(sorted(rows, key=lambda r: r["minute"]), emom=True)
                if sets:
                    exercices.append(_exercice(info, sets, emom=True))
    payload = {
        "client_uuid": client_uuid,
        "name": name.strip() or "Séance",
        "template_id": template_id,
        "started_at": debut.isoformat(timespec="seconds"),
        "note": (note or "").strip() or None,
        "bodyweight_kg": poids_kg or None,
        "exercises": exercices,
    }
    if duree_min and duree_min > 0:
        payload["worked_from"] = payload["started_at"]
        payload["worked_to"] = (debut + timedelta(minutes=duree_min)).isoformat(timespec="seconds")
    return payload


def formulaire_depuis_detail(detail: dict) -> dict:
    """État du formulaire d'édition à partir de `workout_db.get_session_detail`.

    Seules les séries validées sont reprises. Les exercices à minute EMOM sont regroupés en un seul bloc."""
    elements: list[dict] = []
    emom_infos: list[dict] = []
    emom_rows: list[dict] = []
    for ex in detail.get("exercises", []):
        info = {
            "name": ex["name"],
            "create": False,
            "load_formula": ex.get("load_formula") or "weight",
            "unit": ex.get("unit") or "reps",
        }
        sets = [s for s in ex["sets"] if s.get("completed")]
        if not sets:
            continue
        if any(s.get("emom_minute") for s in sets):
            emom_infos.append(info)
            for s in sets:
                emom_rows.append(_ligne_depuis_base(s, exercice=ex["name"]))
        else:
            elements.append(
                {"kind": "exo", "info": info, "rows": [_ligne_depuis_base(s) for s in sets]}
            )
    if emom_rows:
        emom_rows.sort(key=lambda r: r["minute"] or 0)
        elements.append({"kind": "emom", "infos": emom_infos, "rows": emom_rows})

    debut = detail.get("started_at") or f"{detail['date_entry']}T18:00:00"
    return {
        "name": detail["name"],
        "debut": datetime.fromisoformat(debut),
        "duree_min": detail.get("duration_min"),
        "poids_kg": detail.get("bodyweight_kg"),
        "template_id": detail.get("template_id"),
        "note": detail.get("note") or "",
        "elements": elements,
    }


def _ligne_depuis_base(s: dict, exercice: str | None = None) -> dict:
    ligne = {
        "type": _type_depuis_base(s["set_type"]),
        "side": s.get("side"),
        "kg": float(s["weight_kg"]),
        "reps": float(s["reps"]),
        "rpe": s.get("rpe"),
        "minute": s.get("emom_minute"),
        "duree_s": s.get("duration_s"),
    }
    if exercice is not None:
        ligne["exercice"] = exercice
    return ligne
