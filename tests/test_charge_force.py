"""Cohérence du coût de force : monotonie, seuil de 20 % de VL, replis, isométrie, EMOM.

Fixtures synthétiques uniquement. Les constantes du modèle sont des hypothèses : ces tests vérifient
la cohérence interne et les propriétés attendues du doc, pas une vérité physiologique.
"""

from __future__ import annotations

import pytest

from src.core.charge import force
from src.core.charge.force import force_load, force_load_detail, rir_to_vl, stress_multiplier


def _sets(load, reps, n=1, **extra):
    return [
        {"set_type": "N", "load_kg": load, "reps": reps, "completed": 1, **extra} for _ in range(n)
    ]


def _session(sets, e1rm=100.0, **ex_extra):
    return {"exercises": [{"name": "x", "unit": "reps", "e1rm_kg": e1rm, "sets": sets, **ex_extra}]}


def test_monotone_charge_reps_series():
    base = force_load(_session(_sets(80, 5, 3), e1rm=120))
    assert force_load(_session(_sets(90, 5, 3), e1rm=120)) > base
    assert force_load(_session(_sets(80, 6, 3), e1rm=120)) > base
    assert force_load(_session(_sets(80, 5, 4), e1rm=120)) > base


def test_monotone_sans_e1rm_fourni():
    # e1RM estimé dans la séance : plus de charge à reps égales => coût plus élevé
    low = force_load(_session(_sets(60, 5, 3), e1rm=None))
    high = force_load(_session(_sets(100, 5, 3), e1rm=None))
    assert high > low > 0


def test_serie_lourde_courte_vs_longue_legere():
    # sans information d'effort : l'intensité relative pèse (I^2), 10x1 a 95 % > 15 a 65 %
    heavy = force_load_detail(_session(_sets(95, 1, 10)))
    light = force_load_detail(_session(_sets(65, 15)))
    assert heavy.neural > light.neural
    # une seule série : le simple a 95 % coûte moins qu'une série de 15 à 65 % proche de l'échec
    single = force_load(_session(_sets(95, 1, rpe=9)))
    long_set = force_load(_session(_sets(65, 15, rpe=9)))
    assert single < long_set
    # 10 simples a RPE 6 (RIR 4) et 15 reps a 65 % a RPE 9 : même ordre de grandeur (pas de x2)
    ten_singles = force_load(_session(_sets(95, 1, 10, rpe=6)))
    assert 0.5 < ten_singles / long_set < 2.0


def test_multiplicateur_exponentiel_au_dela_de_20_pourcent():
    m = stress_multiplier
    assert m(0.0) == 1.0
    assert m(0.10) < m(0.20) < m(0.30) < m(0.40) < m(0.50)
    # convexité : la hausse de 20 -> 30 % dépasse celle de 10 -> 20 %, et 30 -> 40 % celle de 20 -> 30 %
    assert m(0.30) / m(0.20) > m(0.20) / m(0.10)
    assert m(0.40) / m(0.30) > m(0.30) / m(0.20)


def test_vl_mesuree_augmente_le_cout_et_methode_vbt():
    costs = [force_load(_session(_sets(80, 5, 3, vl=v))) for v in (0.05, 0.20, 0.35)]
    assert costs == sorted(costs) and costs[0] < costs[2]
    d = force_load_detail(_session(_sets(80, 5, 3, vl=0.2)))
    assert (d.method, d.confidence) == ("vbt", "élevé")


def test_vl_en_pourcentage_et_proxy_temporel():
    assert force_load(_session(_sets(80, 5, vl=25))) == pytest.approx(
        force_load(_session(_sets(80, 5, vl=0.25)))
    )
    # durées concentriques 1,0 s -> 1,25 s : VL = 1 - 1/1,25 = 20 %
    assert force.vl_from_rep_durations([1.0, 1.1, 1.25]) == pytest.approx(0.2)
    assert force.vl_from_rep_durations([1.0]) is None
    a = force_load(_session(_sets(80, 5, rep_durations_s=[1.0, 1.1, 1.25])))
    assert a == pytest.approx(force_load(_session(_sets(80, 5, vl=0.2))))


def test_repli_rpe_puis_defaut():
    none = force_load_detail(_session(_sets(80, 5, 3)))
    assert (none.method, none.confidence) == ("defaut", "faible")
    rpe = force_load_detail(_session(_sets(80, 5, 3, rpe=8)))
    assert (rpe.method, rpe.confidence) == ("rpe", "moyen")
    # RPE plus haut => RIR plus bas => VL plus haute => coût plus élevé
    c = [force_load(_session(_sets(80, 5, 3, rpe=r))) for r in (6, 8, 10)]
    assert c == sorted(c) and c[0] < c[2]
    # RPE 10 (échec) > RIR par défaut ; un RPE 5 (RIR 5) coûte moins que le défaut (RIR 3)
    assert c[2] > none.value > force_load(_session(_sets(80, 5, 3, rpe=5)))
    mixed = force_load_detail(_session(_sets(80, 5, 1, rpe=8) + _sets(80, 5, 1)))
    assert mixed.method == "mixte"


def test_serie_type_f_vaut_echec_sans_rpe():
    f = force_load(_session([{**s, "set_type": "F"} for s in _sets(80, 5, 2)]))
    n = force_load(_session(_sets(80, 5, 2)))
    assert f > n


def test_rir_to_vl_points_du_doc():
    assert rir_to_vl(0) == pytest.approx(0.40)  # doc : 35-45 %
    assert rir_to_vl(2) == pytest.approx(0.225)  # doc : 20-25 %
    assert rir_to_vl(4) == pytest.approx(0.125)  # doc : 10-15 %
    assert rir_to_vl(3) == pytest.approx(0.175)
    assert rir_to_vl(-1) == pytest.approx(0.40)
    assert rir_to_vl(99) == 0.0


def test_repli_ultime_srpe_et_absence_de_donnees():
    d = force_load_detail({"exercises": [], "duration_min": 60, "rpe": 7})
    assert d.method == "srpe" and d.confidence == "faible"
    assert d.value == pytest.approx(60 * 7 * force.SRPE_UA)
    d = force_load_detail({"exercises": [], "duration_min": 60})
    assert d.value == pytest.approx(60 * force.SRPE_RPE_DEFAULT * force.SRPE_UA)
    d = force_load_detail(
        {"exercises": [], "started_at": "2030-01-01T10:00:00", "finished_at": "2030-01-01T10:30:00"}
    )
    assert d.value == pytest.approx(30 * force.SRPE_RPE_DEFAULT * force.SRPE_UA)
    d = force_load_detail({"exercises": []})
    assert (d.value, d.method, d.confidence) == (0.0, "aucune", "nul")


def test_ignore_echauffement_et_series_non_validees():
    base = _sets(80, 5, 3)
    noisy = base + [{"set_type": "W", "load_kg": 40, "reps": 8, "completed": 1}]
    noisy += [{"set_type": "N", "load_kg": 80, "reps": 5, "completed": 0}]
    assert force_load(_session(noisy)) == pytest.approx(force_load(_session(base)))


def test_masse_systemique_recalculee_sans_load_kg():
    ex = {"load_formula": "bw_plus_weight", "bw_fraction": 0.955}
    assert force.masse_systemique(20, 80, **ex) == pytest.approx(96.4)
    assert force.masse_systemique(20, 80) == 20
    with_bw = {
        "bodyweight_kg": 80,
        "exercises": [
            {
                "unit": "reps",
                "load_formula": "bw_plus_weight",
                "bw_fraction": 1.0,
                "sets": [{"set_type": "N", "weight_kg": 20, "reps": 5}],
            }
        ],
    }
    lest = force_load(with_bw)
    with_bw["exercises"][0]["sets"][0]["weight_kg"] = 0
    assert 0 < force_load(with_bw) < lest  # le poids du corps compte même sans lest


def test_rep_factor_zero_exclu_du_volume():
    d = force_load_detail(_session(_sets(30, 20, 3), rep_factor=0.0))
    assert d.value == 0.0 and "iso_sans_duree" in d.flags  # rien à compter, signalé
    mix = {
        "exercises": [
            {"unit": "reps", "e1rm_kg": 100, "sets": _sets(80, 5, 3)},
            {"unit": "reps", "rep_factor": 0.0, "sets": _sets(30, 20, 3)},
        ]
    }
    assert force_load(mix) == pytest.approx(force_load(_session(_sets(80, 5, 3))))


def test_isometrie_duree_sous_tension_sans_fti():
    short = force_load_detail(_session(_sets(0, 30), unit="sec"))
    long = force_load_detail(_session(_sets(0, 60), unit="sec"))
    assert long.iso_tut_s == 60 and short.iso_tut_s == 30
    assert long.value == pytest.approx(2 * short.value) and short.method == "isometrie"
    # rep_factor 0 avec durée renseignée : comptée côté isométrie, pas côté tonnage
    d = force_load_detail(_session(_sets(30, 20, 2, duration_s=40), rep_factor=0.0))
    assert d.iso_tut_s == 80 and d.n_sets == 0 and d.value > 0
    # le RPE module l'isométrie
    hard = force_load(_session(_sets(0, 30, rpe=10), unit="sec"))
    easy = force_load(_session(_sets(0, 30, rpe=5), unit="sec"))
    assert hard > easy


def test_emom_densite_intervalle_court_coute_plus():
    def emom(interval):
        sets = [{**s, "emom_minute": i + 1} for i, s in enumerate(_sets(90, 2, 8))]
        return force_load(_session(sets, emom_interval_sec=interval))

    assert emom(30) > emom(60) > emom(120) > 0
    plain = force_load(_session(_sets(90, 2, 8)))
    assert emom(60) > plain  # la 2e minute et suivantes portent un déficit de PCr
    # avec RPE renseigné, l'effort est déjà capté : pas de surcoût de densité
    with_rpe = [{**s, "emom_minute": i + 1} for i, s in enumerate(_sets(90, 2, 8, rpe=7))]
    assert force_load(_session(with_rpe, emom_interval_sec=30)) == pytest.approx(
        force_load(_session(_sets(90, 2, 8, rpe=7)))
    )


def test_series_aberrantes_plafonnees_et_signalees():
    d = force_load_detail(_session(_sets(10, 200)))
    assert "reps>cap" in d.flags
    assert d.value == pytest.approx(force_load(_session(_sets(10, force.REPS_CAP))), rel=1e-9)


def test_activite_intervals_liee_signalee_sans_changer_la_valeur():
    s = _session(_sets(80, 5, 3))
    linked = {**s, "intervals_activity_id": "i123"}
    assert "activite_intervals_liee" in force_load_detail(linked).flags
    assert force_load(linked) == force_load(s)


def test_force_load_est_un_float():
    assert isinstance(force_load(_session(_sets(80, 5))), float)
