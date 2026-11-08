"""Axe force : coût d'une séance de musculation (indice VBT-Load avec repli RIR/RPE).

Contrat partagé : `force_load(session) -> float`. `force_load_detail(session)` renvoie en plus la
méthode utilisée et le niveau de confiance (`ForceLoad`).

Formule (reconstruction : les images de formules de `Quantification Charge Entraînement Force.md`,
section 5.3, ne sont pas lisibles ; la structure vient du texte, toutes les constantes sont des
HYPOTHÈSES non calibrées, voir `docs/charge-force.md`) :

    coût_série = tonnage × I^p × M(VL)            (tonnage = charge systémique × reps × rep_factor)
    coût_séance = (Σ coût_série) × UA_PAR_TONNE + coût isométrique

- Charge systémique : `load_kg` stocké (lest + poids du corps × `bw_fraction`), sinon recalculée.
- I = charge / e1RM, e1RM d'Epley (charge × (1 + reps/30)), meilleure série de l'exercice dans la
  séance (reps <= 12, reps + RIR si RPE connu) ou `e1rm_kg` fourni (historique, à préférer).
- M(VL) = (1 + a·min(VL, 20 %)/20 %) × exp(k·max(0, VL − 20 %)) : exponentielle au-delà de 20 %.
- VL, par ordre de préférence : mesuré (`vl` ou durées concentriques) > RPE (RIR = 10 − RPE) >
  type de série « F » (échec supposé) > RIR par défaut. Sans aucune série exploitable : sRPE
  (durée × RPE). Rien du tout : 0.
- Isométrie (`unit == "sec"`, ou `rep_factor == 0` avec `duration_s`) : durée sous tension, sans FTI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

# --- Constantes : toutes des hypothèses (aucune vérité terrain locale : ni CMJ ni capteur de vitesse) ---
EPLEY_DIV = 30.0  # Epley : 1RM = charge × (1 + reps / 30)
E1RM_MAX_REPS = 12  # au-delà, Epley est trop imprécis pour estimer un 1RM
INTENSITY_FLOOR = 0.30  # plancher de I (évite des poids quasi nuls sur charges très légères)
INTENSITY_EXP = 2.0  # poids de l'intensité relative : I^2 (hypothèse, le doc ne chiffre pas)
VL_THRESHOLD = 0.20  # seuil de 20 % de perte de vitesse (doc, section 2.2 et conclusion)
VL_K = 5.0  # raideur de l'exponentielle : VL 40 % -> x2,7 ; VL 50 % -> x4,5
VL_BASE_GAIN = 0.25  # surcoût linéaire de 0 à 20 % de VL (+25 % à 20 %)
# RIR -> VL : 0 / 2 / 4 = milieux des fourchettes du doc (40, 22,5, 12,5 %) ; 6 et 10 extrapolés.
RIR_VL_POINTS = ((0.0, 0.40), (2.0, 0.225), (4.0, 0.125), (6.0, 0.05), (10.0, 0.0))
RIR_DEFAULT = 3.0  # RIR supposé sans aucune information d'effort
REPS_CAP = 30  # au-delà, les répétitions ne sont pas comptées (série aberrante signalée)
UA_PAR_TONNE = 10.0  # échelle : tonnes pondérées -> unités arbitraires (UA)
# EMOM : demi-vie de resynthèse de la PCr 30 s (doc : 21-57 s ; ~72 % resynthétisés en 55 s).
PCR_HALF_LIFE_S = 30.0
EMOM_DEFAULT_INTERVAL_S = 60.0
EMOM_SECONDS_PER_REP = 3.0
EMOM_DENSITY_GAIN = 0.5  # +50 % du coût par unité de déficit de PCr accumulé (hypothèse)
# Isométrie : UA par minute sous tension à intensité maximale ; pas de force mesurée -> pas de FTI.
ISO_UA_PER_MIN = 3.0
ISO_INTENSITY_DEFAULT = 0.7
# sRPE (repli ultime) : UA par point de sRPE ; RPE de séance supposé sans information.
SRPE_UA = 0.14
SRPE_RPE_DEFAULT = 6.0

CONFIDENCE_NONE = "nul"


@dataclass(frozen=True)
class ForceLoad:
    value: float  # coût total en UA
    method: str  # vbt | rpe | type_f | defaut | mixte | isometrie | srpe | aucune
    confidence: str  # élevé | moyen | faible | nul
    neural: float = 0.0  # part « tonnage × I^p » sans multiplicateur de VL (stress neural), UA
    iso_tut_s: float = 0.0  # durée sous tension isométrique cumulée
    shares: dict[str, float] = field(
        default_factory=dict
    )  # part du coût dynamique par source de VL
    n_sets: int = 0  # séries dynamiques comptées
    flags: tuple[
        str, ...
    ] = ()  # anomalies : reps>cap, iso_sans_duree, volume_stocke_different, ...


def masse_systemique(
    weight_kg: float, bodyweight_kg: float, load_formula: str = "weight", bw_fraction: float = 1.0
) -> float:
    """Charge systémique : lest + poids du corps × fraction (De Leva : 0,955 traction, 0,88 squat)."""
    if load_formula == "bw_plus_weight":
        return bodyweight_kg * bw_fraction + weight_kg
    return weight_kg


def rir_to_vl(rir: float) -> float:
    """VL (fraction) attendue pour un RIR donné, interpolation linéaire entre les points du doc."""
    if rir <= RIR_VL_POINTS[0][0]:
        return RIR_VL_POINTS[0][1]
    for (r0, v0), (r1, v1) in zip(RIR_VL_POINTS, RIR_VL_POINTS[1:], strict=False):
        if rir <= r1:
            return v0 + (v1 - v0) * (rir - r0) / (r1 - r0)
    return RIR_VL_POINTS[-1][1]


def vl_from_rep_durations(durations_s: list[float]) -> float | None:
    """VL ≈ 1 − t_première / t_dernière (proxy temporel concentrique, trajectoire supposée constante)."""
    d = [x for x in durations_s if x and x > 0]
    if len(d) < 2:
        return None
    return min(max(1.0 - d[0] / d[-1], 0.0), 1.0)


def stress_multiplier(vl: float) -> float:
    """Multiplicateur de contrainte M(VL) : 1 à VL nul, exponentiel au-delà de 20 %."""
    vl = min(max(vl, 0.0), 1.0)
    base = 1.0 + VL_BASE_GAIN * min(vl, VL_THRESHOLD) / VL_THRESHOLD
    return base * math.exp(VL_K * max(0.0, vl - VL_THRESHOLD))


def _vl_of_set(s: dict) -> tuple[float, str]:
    """(VL en fraction, source) : mesuré > RPE > type F > défaut."""
    vl = s.get("vl")
    if vl is not None:
        return (vl / 100.0 if vl > 1.0 else float(vl)), "vbt"
    measured = vl_from_rep_durations(s.get("rep_durations_s") or [])
    if measured is not None:
        return measured, "vbt"
    if s.get("rpe") is not None:
        return rir_to_vl(max(0.0, 10.0 - float(s["rpe"]))), "rpe"
    if s.get("set_type") == "F":  # « F » = échec (hypothèse : sens non documenté dans la base)
        return rir_to_vl(0.0), "type_f"
    return rir_to_vl(RIR_DEFAULT), "defaut"


def _rir_of_set(s: dict) -> float:
    if s.get("rpe") is not None:
        return max(0.0, 10.0 - float(s["rpe"]))
    return 0.0


def _set_load(s: dict, ex: dict, bodyweight: float) -> float:
    if s.get("load_kg") is not None:
        return float(s["load_kg"])
    return masse_systemique(
        float(s.get("weight_kg") or 0.0),
        bodyweight,
        ex.get("load_formula", "weight"),
        float(ex.get("bw_fraction", 1.0)),
    )


def _is_isometric(s: dict, ex: dict) -> bool:
    if ex.get("unit") == "sec":
        return True
    return float(ex.get("rep_factor", 1.0)) == 0.0 and bool(s.get("duration_s"))


def _e1rm(rows: list[tuple[float, float, float]]) -> float:
    """e1RM (Epley) d'un exercice : (charge, reps effectives, RIR) -> meilleure estimation."""
    best = 0.0
    for load, reps, rir in rows:
        if load > 0 and 0 < reps <= E1RM_MAX_REPS:
            best = max(best, load * (1.0 + (reps + rir) / EPLEY_DIV))
    return best


def _emom_residual(interval_s: float, reps: float) -> float:
    """Part de PCr non resynthétisée entre deux minutes d'EMOM."""
    rest = max(interval_s - reps * EMOM_SECONDS_PER_REP, 0.0)
    return 2.0 ** (-rest / PCR_HALF_LIFE_S)


def _duration_min(session: dict) -> float | None:
    if session.get("duration_min"):
        return float(session["duration_min"])
    try:
        a = datetime.fromisoformat(session["started_at"])
        b = datetime.fromisoformat(session["finished_at"])
    except (KeyError, TypeError, ValueError):
        return None
    minutes = (b - a).total_seconds() / 60.0
    return minutes if minutes > 0 else None


def _confidence(shares: dict[str, float]) -> str:
    vbt = shares.get("vbt", 0.0)
    effort = vbt + shares.get("rpe", 0.0)
    if vbt >= 0.8:
        return "élevé"
    if effort >= 0.5:
        return "moyen"
    return "faible"


def force_load_detail(session: dict) -> ForceLoad:
    """Coût d'une séance de force. `session` : forme de `workout_db.get_session_detail` (clés
    `bodyweight_kg`, `duration_min`, `exercises[{name, unit, load_formula, rep_factor, bw_fraction,
    emom_interval_sec, e1rm_kg, sets[{set_type, weight_kg, load_kg, reps, completed, rpe, duration_s,
    emom_minute, vl, rep_durations_s}]}]`). Les séries d'échauffement (« W ») et non validées sont ignorées."""
    bodyweight = float(session.get("bodyweight_kg") or 0.0)
    cost_by_src: dict[str, float] = {}
    neural = iso_cost = iso_tut = 0.0
    n_sets = 0
    flags: set[str] = set()
    tonnage_check = 0.0
    rpes: list[float] = []

    for ex in session.get("exercises", []):
        rep_factor = float(ex.get("rep_factor", 1.0))
        for s in ex.get(
            "sets", []
        ):  # volume déclaré : toutes séries validées, échauffement compris
            if s.get("completed", 1) and ex.get("unit") != "sec":
                tonnage_check += _set_load(s, ex, bodyweight) * (s.get("reps") or 0) * rep_factor
        work = [
            s
            for s in ex.get("sets", [])
            if s.get("completed", 1) and s.get("set_type") != "W" and (s.get("reps") or 0) > 0
        ]
        rows = []
        for s in work:
            if s.get("rpe") is not None:
                rpes.append(float(s["rpe"]))
            if _is_isometric(s, ex):
                tut = float(s.get("duration_s") or s["reps"])
                iso_tut += tut
                inten = (
                    float(s["rpe"]) / 10.0 if s.get("rpe") is not None else ISO_INTENSITY_DEFAULT
                )
                iso_cost += ISO_UA_PER_MIN * tut / 60.0 * inten**INTENSITY_EXP
            elif rep_factor == 0.0:
                flags.add("iso_sans_duree")  # isométrie courte exclue du volume (rep_factor = 0)
            else:
                rows.append(s)
        loads = {id(s): _set_load(s, ex, bodyweight) for s in rows}
        e1rm = float(ex.get("e1rm_kg") or 0.0) or _e1rm(
            [(loads[id(s)], s["reps"] * rep_factor, _rir_of_set(s)) for s in rows]
        )
        is_emom = ex.get("emom_interval_sec") or any(s.get("emom_minute") is not None for s in rows)
        interval = float(ex.get("emom_interval_sec") or EMOM_DEFAULT_INTERVAL_S)
        ordered = sorted(rows, key=lambda s: s.get("emom_minute") or 0) if is_emom else rows
        deficit = 0.0
        for s in ordered:
            load = loads[id(s)]
            reps = float(s["reps"])
            if reps > REPS_CAP:
                flags.add("reps>cap")
            if load <= 0:
                continue
            eff_reps = min(reps, REPS_CAP) * rep_factor
            inten = max(min(load / e1rm, 1.0), INTENSITY_FLOOR) if e1rm > 0 else INTENSITY_FLOOR
            vl, src = _vl_of_set(s)
            mult = stress_multiplier(vl)
            if is_emom:
                if src == "defaut":
                    mult *= 1.0 + EMOM_DENSITY_GAIN * deficit
                deficit = (deficit + 1.0) * _emom_residual(interval, reps)
            base = load * eff_reps * inten**INTENSITY_EXP / 1000.0 * UA_PAR_TONNE
            neural += base
            cost_by_src[src] = cost_by_src.get(src, 0.0) + base * mult
            n_sets += 1

    dyn = sum(cost_by_src.values())
    declared = session.get("session_volume_kg")
    if declared and abs(tonnage_check - declared) > 0.05 * max(declared, 1.0):
        flags.add("volume_stocke_different")
    if session.get("intervals_activity_id"):
        flags.add("activite_intervals_liee")  # risque de double comptage avec l'axe endurance

    total = dyn + iso_cost
    if total <= 0:
        duration = _duration_min(session)
        if duration is None:
            return ForceLoad(0.0, "aucune", CONFIDENCE_NONE, flags=tuple(sorted(flags)))
        rpe = session.get("rpe") or (sum(rpes) / len(rpes) if rpes else SRPE_RPE_DEFAULT)
        return ForceLoad(
            duration * float(rpe) * SRPE_UA, "srpe", "faible", flags=tuple(sorted(flags))
        )

    shares = {k: v / dyn for k, v in cost_by_src.items()} if dyn > 0 else {}
    if dyn <= 0:
        method, confidence = "isometrie", "faible"
    else:
        sources = set(shares)
        method = next(iter(sources)) if len(sources) == 1 else "mixte"
        confidence = _confidence(shares)
    return ForceLoad(
        value=total,
        method=method,
        confidence=confidence,
        neural=neural,
        iso_tut_s=iso_tut,
        shares=shares,
        n_sets=n_sets,
        flags=tuple(sorted(flags)),
    )


def force_load(session: dict) -> float:
    """Coût d'une séance de force en UA (voir `force_load_detail` pour la méthode et la confiance)."""
    return force_load_detail(session).value
