"""Readiness : deux axes de charge (endurance, force) + HRV lissée -> forme, fatigue, readiness.

Décision de l'utilisateur : deux axes séparés, chacun avec son CTL/ATL (moyennes exponentielles) et ses
constantes de temps, puis un indice combiné. Fonction pure : aucune lecture de base, aucune dépendance
à `endurance.py` ; les charges journalières sont passées en entrée.

Constantes de temps (jours) — HYPOTHÈSES, sauf l'endurance (42/7, convention Banister/Intervals.icu) :
- force, ATL = 2 j : le doc (`Quantification Charge Entraînement Force.md`, tableau 1) donne une
  restauration du CMJ en 24-48 h (VL 15-25 %) à 48-72 h (VL 30-40 %). Avec τ = 2 j il reste 37 % de
  la fatigue à 48 h et 22 % à 72 h. Aucune source ne fixe τ : choix de cohérence avec ces délais.
- force, CTL = 28 j : plus court que l'endurance (adaptation neuro-musculaire plus labile) — SANS source.

Indice : `forme` = moyenne pondérée de (CTL − ATL)/CTL par axe (TSB relatif, > 0 = reposé), `fatigue` =
axe limitant, max des ATL/CTL (une fatigue neurale ne doit pas être masquée par une endurance reposée),
`readiness` ∈ [0, 100] = 50 + 50 × (mélange de la forme et du z-score de l'HRV lissée).
L'HRV est moyennée sur 4 j en ln(rMSSD) (Plews et al., cité par le doc, section 5.2).
Les poids et échelles sont des hypothèses non validées (ni CMJ ni vérité terrain locale).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

TAU_ENDURANCE = (42.0, 7.0)  # (CTL, ATL)
TAU_FORCE = (28.0, 2.0)  # hypothèses, voir l'en-tête
HRV_WINDOW_DAYS = 4  # doc : moyenne mobile de 3 à 4 jours
HRV_BASELINE_DAYS = 28  # hypothèse
HRV_SD_FLOOR = 0.05  # écart-type minimal du ln(HRV) (~5 %), évite des z-scores explosifs
WARMUP_DAYS = 14  # amorce CTL/ATL à la charge moyenne des premiers jours (hypothèse)
FORME_SCALE = 0.5  # TSB relatif donnant le score de charge maximal (+/- 50 %)
HRV_Z_SCALE = 2.0  # z-score donnant le score HRV maximal
W_HRV = 0.4  # poids de l'HRV dans readiness quand elle est disponible
COLUMNS = ["ctl_e", "atl_e", "ctl_f", "atl_f", "forme", "fatigue", "readiness"]
_EPS = 1e-9


def _daily(series: pd.Series | None, index: pd.DatetimeIndex) -> pd.Series:
    if series is None or len(series) == 0:
        return pd.Series(0.0, index=index)
    s = pd.Series(series.to_numpy(dtype=float), index=pd.to_datetime(series.index).normalize())
    return s.groupby(level=0).sum().reindex(index).fillna(0.0)


def _ewma(loads: np.ndarray, tau: float, seed: float) -> np.ndarray:
    """x_t = x_{t-1} + (charge_t − x_{t-1}) × (1 − exp(−1/τ))."""
    alpha = 1.0 - math.exp(-1.0 / tau)
    out = np.empty(len(loads))
    x = seed
    for i, load in enumerate(loads):
        x += (load - x) * alpha
        out[i] = x
    return out


def hrv_zscore(
    hrv: pd.Series,
    index: pd.DatetimeIndex,
    window: int = HRV_WINDOW_DAYS,
    baseline_days: int = HRV_BASELINE_DAYS,
) -> pd.Series:
    """z-score de ln(HRV) lissée sur `window` jours par rapport à la base glissante de `baseline_days`."""
    h = pd.Series(hrv.to_numpy(dtype=float), index=pd.to_datetime(hrv.index).normalize())
    h = h[h > 0].groupby(level=0).last().reindex(index)
    ln = np.log(h)
    smooth = ln.rolling(window, min_periods=2).mean()
    base = ln.rolling(baseline_days, min_periods=7)
    sd = base.std().clip(lower=HRV_SD_FLOOR)
    return ((smooth - base.mean()) / sd).clip(-3.0, 3.0)


def readiness(
    daily_endurance: pd.Series,
    daily_force: pd.Series,
    hrv: pd.Series | None = None,
    *,
    tau_endurance: tuple[float, float] = TAU_ENDURANCE,
    tau_force: tuple[float, float] = TAU_FORCE,
    w_endurance: float = 0.5,
    w_force: float = 0.5,
    warmup_days: int = WARMUP_DAYS,
) -> pd.DataFrame:
    """DataFrame journalier [ctl_e, atl_e, ctl_f, atl_f, forme, fatigue, readiness] (+ `hrv_z`).

    Entrées : séries indexées par date (charge du jour ; jours absents = 0) et HRV optionnelle
    (jours sans mesure ignorés). `warmup_days` = 0 amorce CTL/ATL à zéro ; sinon à la charge moyenne
    des `warmup_days` premiers jours. Un axe sans aucune charge est exclu de forme/fatigue."""
    parts = [s for s in (daily_endurance, daily_force) if s is not None and len(s)]
    if not parts:
        return pd.DataFrame(columns=[*COLUMNS, "hrv_z"], dtype=float)
    dates = pd.to_datetime(np.concatenate([p.index.to_numpy() for p in parts])).normalize()
    index = pd.date_range(dates.min(), dates.max(), freq="D")
    cols: dict[str, np.ndarray] = {}
    for key, series, (tc, ta) in (
        ("e", daily_endurance, tau_endurance),
        ("f", daily_force, tau_force),
    ):
        loads = _daily(series, index).to_numpy()
        seed = float(loads[:warmup_days].mean()) if warmup_days > 0 else 0.0
        cols[f"ctl_{key}"] = _ewma(loads, tc, seed)
        cols[f"atl_{key}"] = _ewma(loads, ta, seed)
    out = pd.DataFrame(cols, index=index)

    rel, acwr, weights = [], [], []
    for key, w in (("e", w_endurance), ("f", w_force)):
        ctl, atl = out[f"ctl_{key}"], out[f"atl_{key}"]
        ok = ctl > _EPS
        safe = ctl.where(ok)
        rel.append(((ctl - atl) / safe).to_numpy())
        acwr.append((atl / safe).to_numpy())
        weights.append(np.where(ok, w, 0.0))
    rel_a, acwr_a, w_a = np.array(rel), np.array(acwr), np.array(weights)
    wsum = w_a.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        forme = np.nansum(np.nan_to_num(rel_a) * w_a, axis=0) / np.where(wsum > 0, wsum, np.nan)
        fatigue = np.where(wsum > 0, np.nanmax(np.nan_to_num(acwr_a, nan=-np.inf), axis=0), np.nan)
    out["forme"] = forme
    out["fatigue"] = fatigue

    s_load = np.clip(out["forme"] / FORME_SCALE, -1.0, 1.0)
    z = hrv_zscore(hrv, index) if hrv is not None and len(hrv) else pd.Series(np.nan, index=index)
    s_hrv = np.clip(z / HRV_Z_SCALE, -1.0, 1.0)
    mix = np.where(
        s_hrv.isna(),
        s_load,
        np.where(s_load.isna(), s_hrv, (1 - W_HRV) * s_load + W_HRV * s_hrv),
    )
    out["readiness"] = 50.0 + 50.0 * mix
    out["hrv_z"] = z
    return out[[*COLUMNS, "hrv_z"]]
