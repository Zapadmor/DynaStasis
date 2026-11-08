"""Readiness : deux axes séparés (CTL/ATL propres) + HRV lissée. Données synthétiques."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.core.charge import readiness as rd
from src.core.charge.readiness import readiness


def _series(values, start="2030-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


def test_colonnes_et_longueur_journaliere():
    out = readiness(_series([50] * 10), _series([30] * 10))
    assert list(out.columns[:7]) == rd.COLUMNS
    assert len(out) == 10 and out.index.is_monotonic_increasing
    # jours manquants comblés par 0 charge
    sparse = pd.Series([40.0, 40.0], index=pd.to_datetime(["2030-01-01", "2030-01-05"]))
    assert len(readiness(sparse, None)) == 5


def test_regime_constant_forme_nulle_et_readiness_50():
    out = readiness(_series([60] * 200), _series([40] * 200))
    last = out.iloc[-1]
    assert last.ctl_e == pytest.approx(60, rel=1e-3) and last.atl_f == pytest.approx(40, rel=1e-3)
    assert last.forme == pytest.approx(0, abs=1e-3)
    assert last.readiness == pytest.approx(50, abs=0.5)
    assert last.fatigue == pytest.approx(1.0, abs=1e-3)


def test_axes_independants():
    flat = np.full(60, 50.0)
    hard_force = flat.copy()
    hard_force[-1] = 400.0
    a = readiness(_series(flat), _series(flat), warmup_days=0)
    b = readiness(_series(flat), _series(hard_force), warmup_days=0)
    for col in ("ctl_e", "atl_e"):
        assert np.allclose(a[col], b[col])
    assert b.atl_f.iloc[-1] > a.atl_f.iloc[-1]


def test_atl_force_retombe_en_48_72h_et_plus_vite_que_endurance():
    load = np.zeros(30)
    load[0] = 100.0
    out = readiness(_series(load), _series(load), warmup_days=0)
    peak_f, peak_e = out.atl_f.iloc[0], out.atl_e.iloc[0]
    # tau = 2 j : reste ~ 37 % a 48 h et ~ 22 % a 72 h (hypothèse alignée sur le doc)
    assert out.atl_f.iloc[2] / peak_f == pytest.approx(math.exp(-2 / 2.0), rel=1e-6)
    assert out.atl_f.iloc[3] / peak_f < 0.25
    assert out.atl_e.iloc[3] / peak_e > 0.5  # l'ATL endurance (tau 7 j) décroit bien plus lentement


def test_seance_dure_fait_baisser_forme_et_readiness():
    base = np.full(60, 50.0)
    hard = base.copy()
    hard[-1] = 300.0
    a = readiness(_series(base), _series(base))
    b = readiness(_series(base), _series(hard))
    assert b.forme.iloc[-1] < a.forme.iloc[-1] and b.readiness.iloc[-1] < a.readiness.iloc[-1]
    assert b.fatigue.iloc[-1] > a.fatigue.iloc[-1]
    # une fatigue de force ne doit pas etre masquée par une endurance reposée : axe limitant
    assert b.fatigue.iloc[-1] > 1.5


def test_tau_personnalises_pris_en_compte():
    load = np.zeros(10)
    load[0] = 100.0
    slow = readiness(_series(load), None, tau_endurance=(42.0, 20.0), warmup_days=0)
    fast = readiness(_series(load), None, tau_endurance=(42.0, 2.0), warmup_days=0)
    assert slow.atl_e.iloc[5] > fast.atl_e.iloc[5]


def test_axe_sans_charge_exclu_de_la_forme():
    out = readiness(_series([60] * 50), _series([0] * 50))
    assert out.ctl_f.iloc[-1] == 0 and not math.isnan(out.forme.iloc[-1])
    assert out.forme.iloc[-1] == pytest.approx(0, abs=1e-3)
    empty = readiness(pd.Series(dtype=float), None)
    assert empty.empty and list(empty.columns[:7]) == rd.COLUMNS


def _hrv(values):
    return _series(values)


def test_hrv_baisse_diminue_readiness_et_hausse_lamplifie():
    n = 60
    load = _series([50] * n)
    stable = np.full(n, 60.0)
    drop = stable.copy()
    drop[-4:] = 40.0
    rise = stable.copy()
    rise[-4:] = 85.0
    r = {
        k: readiness(load, load, _hrv(v)).readiness.iloc[-1]
        for k, v in {"stable": stable, "drop": drop, "rise": rise}.items()
    }
    assert r["drop"] < r["stable"] < r["rise"]
    assert r["stable"] == pytest.approx(50, abs=1)


def test_hrv_lissee_attenue_un_pic_isole():
    n = 60
    load = _series([50] * n)
    spike = np.full(n, 60.0)
    spike[-1] = 30.0  # une seule mauvaise mesure
    sustained = np.full(n, 60.0)
    sustained[-4:] = 30.0
    z_spike = readiness(load, load, _hrv(spike)).hrv_z.iloc[-1]
    z_sust = readiness(load, load, _hrv(sustained)).hrv_z.iloc[-1]
    assert z_sust < z_spike < 0  # le jour isole pese ~1/4 ; la baisse soutenue 4 j pese plein pot


def test_hrv_absente_ou_lacunaire_repli_sur_la_charge():
    load = _series([50] * 40)
    with_nan = _hrv([np.nan] * 40)
    none = readiness(load, load)
    assert np.allclose(none.readiness, readiness(load, load, with_nan).readiness)
    assert none.hrv_z.isna().all()
    # peu de mesures (moins de 7 jours de base) : pas de z-score, readiness = charge seule
    few = _hrv([np.nan] * 36 + [55, 56, 54, 20])
    assert readiness(load, load, few).readiness.iloc[-1] == pytest.approx(none.readiness.iloc[-1])


def test_fonction_pure_entrees_non_modifiees():
    e, f, h = _series([50] * 30), _series([30] * 30), _hrv([60] * 30)
    snap = [x.copy() for x in (e, f, h)]
    readiness(e, f, h)
    for x, s in zip((e, f, h), snap, strict=True):
        pd.testing.assert_series_equal(x, s)
