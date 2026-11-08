"""Charge d'endurance : données entièrement synthétiques, résultats calculables à la main."""

from __future__ import annotations

import math
import sqlite3

import numpy as np
import pandas as pd
import pytest

from src.core.charge import endurance as e
from src.core.charge import stockage
from src.database import connection

PARAMS = e.HrssParams(rest_hr=50, max_hr=190, lthr=170)


def _flux(n, hr=None, watts=None, speed=None, grade=None):
    flux = {"time": np.arange(n, dtype=float)}
    for nom, valeur in (
        ("heartrate", hr),
        ("watts", watts),
        ("velocity_smooth", speed),
        ("grade_smooth", grade),
    ):
        if valeur is not None:
            flux[nom] = np.full(n, valeur, dtype=float)
    return flux


# ── HRSS ────────────────────────────────────────────────────────────────────


def test_hrss_une_heure_au_seuil_vaut_100():
    assert e.hrss(_flux(3600, hr=170), PARAMS) == pytest.approx(100.0)


def test_hrss_est_proportionnelle_a_la_duree():
    assert e.hrss(_flux(1800, hr=170), PARAMS) == pytest.approx(50.0)


def test_hrss_croit_avec_la_frequence_cardiaque():
    assert e.hrss(_flux(3600, hr=150), PARAMS) < 100 < e.hrss(_flux(3600, hr=180), PARAMS)


def test_hrss_ignore_les_fc_nulles_ou_absentes():
    flux = _flux(3600, hr=170)
    flux["heartrate"][:1800] = 0.0
    flux["heartrate"][1800:2000] = np.nan
    assert e.hrss(flux, PARAMS) == pytest.approx(100.0 * 1600 / 3600)


def test_hrss_sans_flux_cardiaque_vaut_zero():
    assert e.hrss({"time": np.arange(100.0)}, PARAMS) == 0.0
    assert e.hrss({}, PARAMS) == 0.0


def test_hrss_exclut_les_secondes_a_l_arret_si_la_vitesse_est_connue():
    speed = np.r_[np.full(1800, 3.0), np.zeros(1800)]
    flux = {**_flux(3600, hr=170), "velocity_smooth": speed}
    assert e.hrss(flux, PARAMS) == pytest.approx(50.0)


def test_hrss_plafonne_les_trous_de_temps():
    flux = _flux(10, hr=170)
    flux["time"] = np.r_[np.arange(5.0), np.arange(5.0) + 1000.0]  # un trou de 996 s
    # 5 s avant le trou, puis 5 s plafonnées pour le trou, puis 4 s : 14 s au total
    assert e.hrss(flux, PARAMS) == pytest.approx(100.0 * (5 + e.DT_MAX_S + 4) / 3600)


def test_hrss_est_reproductible():
    rng = np.random.default_rng(0)
    flux = _flux(2000, hr=140)
    flux["heartrate"] = 140 + 10 * rng.standard_normal(2000)
    assert e.hrss(flux, PARAMS) == e.hrss(flux, PARAMS)


# ── Puissance ───────────────────────────────────────────────────────────────


def test_puissance_normalisee_constante_egale_la_puissance():
    assert e.normalized_power(np.full(600, 250.0)) == pytest.approx(250.0)


def test_puissance_normalisee_depasse_la_moyenne_si_variable():
    watts = np.tile(np.r_[np.full(60, 100.0), np.full(60, 400.0)], 10)
    assert e.normalized_power(watts) > watts.mean()


def test_tss_une_heure_au_seuil_vaut_100():
    flux = _flux(3600, watts=280)
    assert e.power_tss(flux, 280.0) == pytest.approx(100.0)


def test_tss_croit_comme_le_carre_de_l_intensite():
    flux = _flux(3600, watts=140)
    assert e.power_tss(flux, 280.0) == pytest.approx(25.0)


def test_tss_seuil_nul_ou_flux_absent_donne_zero():
    assert e.power_tss(_flux(100, watts=200), 0.0) == 0.0
    assert e.power_tss(_flux(100, hr=150), 250.0) == 0.0


def test_puissance_critique_retrouve_le_modele_travail_duree():
    efforts = {d: 200 + 18000 / d for d in (180, 300, 720, 1200)}
    assert e.critical_power(efforts) == pytest.approx(200.0)
    assert e.critical_power({300: 300.0}) is None


def test_meilleure_puissance_moyenne():
    watts = np.r_[np.full(100, 100.0), np.full(60, 300.0), np.full(100, 100.0)]
    assert e.best_mean_power(watts, 60) == pytest.approx(300.0)
    assert e.best_mean_power(watts, 1000) is None


# ── Allure ──────────────────────────────────────────────────────────────────


def test_vitesse_ajustee_a_la_pente():
    plat = e.grade_adjusted_speed(np.array([3.0]), np.array([0.0]))
    montee = e.grade_adjusted_speed(np.array([3.0]), np.array([8.0]))
    descente_douce = e.grade_adjusted_speed(np.array([3.0]), np.array([-8.0]))
    assert plat[0] == pytest.approx(3.0)
    assert montee[0] > 3.0
    assert descente_douce[0] < montee[0]


def test_pace_tss_une_heure_a_la_vitesse_seuil_sur_le_plat_vaut_100():
    assert e.pace_tss(_flux(3600, speed=3.5, grade=0.0), 3.5) == pytest.approx(100.0)


def test_pace_tss_la_pente_augmente_la_charge():
    plat = e.pace_tss(_flux(3600, speed=3.0, grade=0.0), 3.5)
    cote = e.pace_tss(_flux(3600, speed=3.0, grade=6.0), 3.5)
    assert cote > plat


def test_vitesse_critique_retrouve_la_pente_distance_duree():
    cs, dprime = 3.5, 800.0
    paires = [(d, (d - dprime) / cs) for d in (5000.0, 10000.0)]
    assert e.critical_speed(paires) == pytest.approx(cs)
    assert e.critical_speed(paires[:1]) is None


# ── Courbe Forme/Fatigue ────────────────────────────────────────────────────


def _charges(valeurs):
    return pd.Series(
        valeurs, index=pd.date_range("2000-01-01", periods=len(valeurs)).strftime("%Y-%m-%d")
    )


def test_pmc_premier_jour_applique_le_facteur_d_amortissement():
    courbe = e.pmc(_charges([100.0, 0.0]))
    assert courbe["ctl"].iloc[0] == pytest.approx(100 * (1 - math.exp(-1 / 42)))
    assert courbe["atl"].iloc[0] == pytest.approx(100 * (1 - math.exp(-1 / 7)))
    assert courbe["tsb"].iloc[0] == pytest.approx(courbe["ctl"].iloc[0] - courbe["atl"].iloc[0])


def test_pmc_tsb_de_la_veille():
    courbe = e.pmc(_charges([100.0, 0.0, 0.0]), tsb_veille=True)
    assert courbe["tsb"].iloc[0] == 0.0
    base = e.pmc(_charges([100.0, 0.0, 0.0]))
    assert courbe["tsb"].iloc[1] == pytest.approx(base["ctl"].iloc[0] - base["atl"].iloc[0])


def test_pmc_charge_constante_converge_vers_la_charge():
    courbe = e.pmc(_charges([60.0] * 400))
    assert courbe["ctl"].iloc[-1] == pytest.approx(60.0, abs=0.5)
    assert courbe["atl"].iloc[-1] == pytest.approx(60.0, abs=1e-3)


def test_pmc_graine_et_repos():
    courbe = e.pmc(_charges([0.0] * 3), seed=(50.0, 40.0))
    assert courbe["ctl"].iloc[0] == pytest.approx(50.0 * math.exp(-1 / 42))
    assert courbe["atl"].iloc[2] == pytest.approx(40.0 * math.exp(-3 / 7))


def test_pmc_est_reproductible():
    charges = _charges([10.0, 0.0, 55.5, 0.0, 30.0])
    assert e.pmc(charges).equals(e.pmc(charges))


def test_pmc_intervals_le_ctl_ignore_les_types_exclus():
    tout = _charges([100.0, 0.0])
    ctl_seul = _charges([40.0, 0.0])
    courbe = e.pmc_intervals(tout, ctl_seul)
    assert courbe["ctl"].iloc[0] == pytest.approx(40 * (1 - math.exp(-1 / 42)))
    assert courbe["atl"].iloc[0] == pytest.approx(100 * (1 - math.exp(-1 / 7)))
    assert "Workout" in e.TYPES_HORS_CTL_INTERVALS


# ── Estimateur fusionné ─────────────────────────────────────────────────────


def test_charge_locale_prefere_la_frequence_cardiaque():
    flux = _flux(3600, hr=170, watts=280, speed=3.5, grade=0.0)
    r = e.charge_locale(flux, PARAMS, (280.0, 0.8), (3.5, 0.6))
    assert (r.methode, r.confiance, r.estime) == ("hrss", "haute", False)
    assert r.valeur == pytest.approx(100.0)


def test_charge_locale_se_replie_sur_la_puissance_puis_l_allure():
    flux = _flux(3600, hr=0, watts=280, speed=3.5, grade=0.0)
    r = e.charge_locale(flux, PARAMS, (280.0, 0.8), (3.5, 0.6))
    assert (r.methode, r.estime) == ("puissance_estimee", True)
    assert r.valeur == pytest.approx(80.0)
    sans_watts = {k: v for k, v in flux.items() if k != "watts"}
    r = e.charge_locale(sans_watts, PARAMS, (280.0, 0.8), (3.5, 0.6))
    assert (r.methode, r.confiance) == ("allure_estimee", "faible")
    assert r.valeur == pytest.approx(60.0)


def test_charge_locale_sans_signal_vaut_zero():
    r = e.charge_locale({"time": np.arange(10.0)}, PARAMS, (280.0, 0.8), (3.5, 0.6))
    assert (r.valeur, r.methode, r.confiance) == (0.0, "aucune", "nulle")


# ── Stockage et migration 014 ───────────────────────────────────────────────


def test_migration_014_cree_la_table_sur_base_en_version_13(db):
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE charge_locale")
        conn.execute("PRAGMA user_version = 13")
    connection.init_db()
    with sqlite3.connect(db) as conn:
        assert (
            conn.execute("PRAGMA user_version").fetchone()[0] == connection.latest_version() >= 14
        )
        colonnes = {r[1] for r in conn.execute("PRAGMA table_info(charge_locale)")}
    assert {"activity_id", "charge", "methode", "confiance", "estime", "version_algo"} <= colonnes


def test_stockage_enregistre_et_remplace(conn):
    stockage.enregistrer_charge_locale(
        conn, "a1", "2000-01-01", e.ChargeLocale(42.0, "hrss", "haute", False)
    )
    stockage.enregistrer_charge_locale(
        conn, "a2", "2000-01-01", e.ChargeLocale(8.0, "allure_estimee", "faible", True)
    )
    stockage.enregistrer_charge_locale(
        conn, "a2", "2000-01-01", e.ChargeLocale(10.0, "allure_estimee", "faible", True)
    )
    assert stockage.charge_locale_par_jour(conn) == {"2000-01-01": 52.0}
    ligne = conn.execute(
        "SELECT estime, version_algo FROM charge_locale WHERE activity_id = 'a2'"
    ).fetchone()
    assert (ligne[0], ligne[1]) == (1, e.VERSION_ALGO)
