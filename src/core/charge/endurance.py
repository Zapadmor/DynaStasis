"""Axe endurance : charge par séance (HRSS, puissance, allure) et modèle Forme/Fatigue.

Contrat partagé :
- `hrss(streams, params) -> float`
- `pmc(daily_loads, seed) -> pandas.DataFrame[ctl, atl, tsb]`

Les « streams » sont des dictionnaires `nom -> suite de valeurs` à 1 point par échantillon
(`time`, `heartrate`, `watts`, `velocity_smooth`, `grade_smooth`). Rien ici n'est appelé par
l'application par défaut : le calcul local est une fonction à appeler explicitement, la source de
vérité reste Intervals.icu (voir docs/charge-endurance.md).

Variante HRSS retenue (voir le rapport pour les variantes écartées) : TRIMP de Banister par seconde,
FC absente ou nulle ignorée, secondes à l'arrêt (vitesse < 0,1 m/s, quand le flux de vitesse existe)
ignorées, normalisée par 1 h à la FC seuil (= 100).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

TAU_CTL = 42.0
TAU_ATL = 7.0
# Types dont la charge compte pour l'ATL mais pas pour le CTL dans l'export Intervals observé
# (vérifié sur 244 jours : 0 écart). C'est une constatation, pas une règle des notes de référence.
TYPES_HORS_CTL_INTERVALS = frozenset({"Workout", "WeightTraining"})
VITESSE_ARRET_MS = 0.1
DT_MAX_S = 5.0


@dataclass(frozen=True)
class HrssParams:
    """Paramètres de la HRSS. `b` et `y` : coefficients de Banister (homme)."""

    rest_hr: float
    max_hr: float
    lthr: float
    b: float = 1.92
    y: float = 0.64


def _array(streams: Mapping[str, Sequence[float]], name: str) -> np.ndarray | None:
    values = streams.get(name)
    if values is None:
        return None
    return np.asarray(values, dtype=float)


def _dt(streams: Mapping[str, Sequence[float]], n: int) -> np.ndarray:
    """Durée représentée par chaque échantillon (s) : écart réel au précédent, plafonné."""
    time = _array(streams, "time")
    if time is None or len(time) != n or n == 0:
        return np.ones(n)
    return np.minimum(np.diff(time, prepend=time[0] - 1.0), DT_MAX_S)


def _trimp_per_minute(x: np.ndarray, b: float, y: float) -> np.ndarray:
    x = np.clip(x, 0.0, None)
    return x * y * np.exp(b * x)


def _mask_en_mouvement(streams: Mapping[str, Sequence[float]], n: int) -> np.ndarray:
    speed = _array(streams, "velocity_smooth")
    if speed is None or len(speed) != n:
        return np.ones(n, dtype=bool)
    return np.nan_to_num(speed) > VITESSE_ARRET_MS


def hrss(streams: Mapping[str, Sequence[float]], params: HrssParams) -> float:
    """Heart Rate Stress Score d'une séance ; 0.0 si aucune FC exploitable."""
    hr = _array(streams, "heartrate")
    if hr is None or len(hr) == 0:
        return 0.0
    hrr = (hr - params.rest_hr) / (params.max_hr - params.rest_hr)
    valid = np.nan_to_num(hr) > 0
    valid &= _mask_en_mouvement(streams, len(hr))
    per_min = np.where(valid, _trimp_per_minute(np.nan_to_num(hrr), params.b, params.y), 0.0)
    dt = _dt(streams, len(hr))
    reference = 60.0 * float(
        _trimp_per_minute(
            np.array([(params.lthr - params.rest_hr) / (params.max_hr - params.rest_hr)]),
            params.b,
            params.y,
        )[0]
    )
    return float(100.0 * np.sum(per_min * dt / 60.0) / reference)


def normalized_power(watts: Sequence[float], window_s: int = 30) -> float:
    """Puissance normalisée : moyenne glissante 30 s, puis moyenne d'ordre 4 (échantillonnage 1 Hz)."""
    p = np.nan_to_num(np.asarray(watts, dtype=float))
    if len(p) == 0:
        return 0.0
    rolled = pd.Series(p).rolling(window_s, min_periods=window_s).mean().dropna().to_numpy()
    if len(rolled) == 0:
        return float(np.mean(p))
    return float(np.mean(rolled**4) ** 0.25)


def tss_from_normalized(duration_s: float, normalized: float, threshold: float) -> float:
    """Charge = N * NP * IF / (seuil * 3600) * 100, IF = NP / seuil. Un seuil nul donne 0."""
    if threshold <= 0 or normalized <= 0:
        return 0.0
    return float(duration_s * normalized * (normalized / threshold) / (threshold * 3600.0) * 100.0)


def power_tss(streams: Mapping[str, Sequence[float]], threshold_w: float) -> float:
    """TSS puissance sur le flux `watts` (secondes à l'arrêt exclues si la vitesse est connue)."""
    watts = _array(streams, "watts")
    if watts is None or len(watts) == 0:
        return 0.0
    duration = float(np.sum(_dt(streams, len(watts)) * _mask_en_mouvement(streams, len(watts))))
    return tss_from_normalized(duration, normalized_power(watts), threshold_w)


def minetti_cost(grade: np.ndarray) -> np.ndarray:
    """Coût énergétique de la course (J/kg/m) selon la pente (fraction), polynôme de Minetti et al. 2002.

    Bornée à +/-0,45 (domaine de validité de l'ajustement).
    """
    i = np.clip(grade, -0.45, 0.45)
    return 155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6


def grade_adjusted_speed(speed: np.ndarray, grade_percent: np.ndarray) -> np.ndarray:
    """Vitesse équivalente à plat (m/s) : v * C(pente) / C(0). `grade_percent` en %."""
    cost = minetti_cost(np.nan_to_num(grade_percent) / 100.0)
    return np.nan_to_num(speed) * cost / minetti_cost(np.zeros(1))[0]


def normalized_graded_speed(streams: Mapping[str, Sequence[float]], window_s: int = 30) -> float:
    """NGP en m/s : même normalisation que la NP, appliquée à la vitesse ajustée à la pente."""
    speed = _array(streams, "velocity_smooth")
    if speed is None or len(speed) == 0:
        return 0.0
    grade = _array(streams, "grade_smooth")
    gap = grade_adjusted_speed(speed, grade if grade is not None else np.zeros(len(speed)))
    return normalized_power(gap, window_s)


def pace_tss(streams: Mapping[str, Sequence[float]], threshold_speed_ms: float) -> float:
    """Pace TSS : même forme que le TSS puissance, avec la NGP et une vitesse seuil (m/s)."""
    speed = _array(streams, "velocity_smooth")
    if speed is None or len(speed) == 0:
        return 0.0
    duration = float(np.sum(_dt(streams, len(speed)) * _mask_en_mouvement(streams, len(speed))))
    return tss_from_normalized(duration, normalized_graded_speed(streams), threshold_speed_ms)


def critical_power(best_efforts: Mapping[float, float]) -> float | None:
    """Puissance critique (W) par régression travail-durée : W = CP * t + W'. `{durée_s: puissance_W}`.

    Estimation : à marquer « estimé » partout où elle sert. None si moins de deux durées.
    """
    if len(best_efforts) < 2:
        return None
    durations = np.array(sorted(best_efforts), dtype=float)
    work = durations * np.array([best_efforts[d] for d in sorted(best_efforts)], dtype=float)
    slope, _ = np.polyfit(durations, work, 1)
    return float(slope)


def best_mean_power(watts: Sequence[float], duration_s: int) -> float | None:
    """Meilleure puissance moyenne sur `duration_s` secondes (1 Hz), None si flux trop court."""
    p = np.nan_to_num(np.asarray(watts, dtype=float))
    if len(p) < duration_s:
        return None
    return float(pd.Series(p).rolling(duration_s).mean().max())


def critical_speed(distance_time_pairs: Sequence[tuple[float, float]]) -> float | None:
    """Vitesse critique (m/s) entre deux performances `(distance_m, durée_s)` : pente D = CS * t + D'."""
    if len(distance_time_pairs) < 2:
        return None
    d = np.array([p[0] for p in distance_time_pairs], dtype=float)
    t = np.array([p[1] for p in distance_time_pairs], dtype=float)
    if np.ptp(t) == 0:
        return None
    return float(np.polyfit(t, d, 1)[0])


VERSION_ALGO = "endurance-1"


@dataclass(frozen=True)
class ChargeLocale:
    """Charge d'une séance avec sa méthode et son niveau de confiance."""

    valeur: float
    methode: str  # hrss | puissance_estimee | allure_estimee | aucune
    confiance: str  # haute | moyenne | faible | nulle
    estime: bool


def charge_locale(
    streams: Mapping[str, Sequence[float]],
    hr_params: HrssParams | None = None,
    puissance: tuple[float, float] | None = None,
    allure: tuple[float, float] | None = None,
) -> ChargeLocale:
    """Estimateur fusionné PROPOSÉ (non adopté) : FC si exploitable, sinon puissance, sinon allure.

    `puissance` = (CP estimée en W, facteur de recalage TSS -> HRSS) ; `allure` = (vitesse seuil estimée en
    m/s, facteur de recalage). Les facteurs viennent d'une régression sur les séances ayant FC et l'autre
    signal. Les deux replis sont marqués « estimé » et de confiance moindre.
    """
    if hr_params is not None:
        valeur = hrss(streams, hr_params)
        if valeur > 0:
            return ChargeLocale(valeur, "hrss", "haute", False)
    if puissance is not None:
        valeur = power_tss(streams, puissance[0]) * puissance[1]
        if valeur > 0:
            return ChargeLocale(valeur, "puissance_estimee", "moyenne", True)
    if allure is not None:
        valeur = pace_tss(streams, allure[0]) * allure[1]
        if valeur > 0:
            return ChargeLocale(valeur, "allure_estimee", "faible", True)
    return ChargeLocale(0.0, "aucune", "nulle", False)


def _ewma(loads: np.ndarray, tau: float, seed: float) -> np.ndarray:
    k = 1.0 - math.exp(-1.0 / tau)
    out = np.empty(len(loads))
    value = seed
    for index, load in enumerate(loads):
        value += (load - value) * k
        out[index] = value
    return out


def pmc(
    daily_loads: pd.Series, seed: tuple[float, float] = (0.0, 0.0), tsb_veille: bool = False
) -> pd.DataFrame:
    """Courbe Forme/Fatigue : colonnes `ctl`, `atl`, `tsb`, indexées comme `daily_loads`.

    `daily_loads` : une charge par jour consécutif (0 les jours sans séance). `seed` : (CTL, ATL) la
    veille du premier jour. TSB = CTL - ATL du même jour (convention observée dans `vigueur_entries` et
    l'export Intervals) ; `tsb_veille=True` donne la convention des notes de référence, CTL(d-1) - ATL(d-1).
    """
    loads = daily_loads.to_numpy(dtype=float)
    ctl = _ewma(loads, TAU_CTL, seed[0])
    atl = _ewma(loads, TAU_ATL, seed[1])
    if tsb_veille:
        tsb = np.r_[seed[0] - seed[1], (ctl - atl)[:-1]] if len(loads) else np.array([])
    else:
        tsb = ctl - atl
    return pd.DataFrame({"ctl": ctl, "atl": atl, "tsb": tsb}, index=daily_loads.index)


def pmc_intervals(
    daily_loads_all: pd.Series, daily_loads_ctl: pd.Series, seed: tuple[float, float] = (0.0, 0.0)
) -> pd.DataFrame:
    """Variante observée chez Intervals : l'ATL reçoit toute la charge, le CTL seulement celle des
    types hors `TYPES_HORS_CTL_INTERVALS`. Le TSB est CTL - ATL du même jour."""
    ctl = _ewma(daily_loads_ctl.to_numpy(dtype=float), TAU_CTL, seed[0])
    atl = _ewma(daily_loads_all.to_numpy(dtype=float), TAU_ATL, seed[1])
    return pd.DataFrame({"ctl": ctl, "atl": atl, "tsb": ctl - atl}, index=daily_loads_all.index)
