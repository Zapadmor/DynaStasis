"""Services Vigueur : phases du macro-cycle et jalons, pauses, charge, listes de séries."""

from __future__ import annotations

import datetime

from src.services import vigueur


def test_statut_phase_bornes_incluses():
    jour = datetime.date(2026, 6, 15)
    assert vigueur.statut_phase("2026-06-16", "2026-07-01", jour) == "À VENIR"
    assert vigueur.statut_phase("2026-06-01", "2026-06-15", jour) == "EN COURS"
    assert vigueur.statut_phase("2026-06-15", "2026-07-01", jour) == "EN COURS"
    assert vigueur.statut_phase("2026-05-01", "2026-06-14", jour) == "PASSÉ"


def test_charge_quotidienne_base_vide(db):
    assert vigueur.charge_quotidienne() == []
    assert vigueur.pauses() == []


def test_charge_quotidienne_ordre_chronologique(demo_db):
    quotidien = vigueur.charge_quotidienne()
    assert quotidien
    dates = [r["date_entry"] for r in quotidien]
    assert dates == sorted(dates)


# ── pauses tracées sur la courbe ─────────────────────────────────────────────

FREEZES = [
    {"date_debut": "2026-07-01", "date_fin": "2026-07-09", "raison": "Randonnée GR20"},
    {"date_debut": "2026-09-07", "date_fin": "2026-09-13", "raison": "Maladie hivernale"},
    {"date_debut": "2026-10-23", "date_fin": "2026-10-30", "raison": "x" * 60},
]


def test_pauses_hors_fenetre_ecartees_et_rognees():
    bandes = vigueur.bandes_pauses(FREEZES, "2026-09-10", "2026-10-25")
    assert bandes[0]["label"].startswith("PAUSE · Maladie")
    assert bandes[1]["label"].startswith("PAUSE · xxxx")
    assert len(bandes) == 2
    assert bandes[0]["x0"] == "2026-09-10"  # rognée au début de la fenêtre
    assert bandes[1]["x1"] == "2026-10-25"  # rognée à la fin de la fenêtre


def test_libelle_de_pause_tronque_et_sans_raison():
    (b,) = vigueur.bandes_pauses(FREEZES[2:], "2026-01-01", "2026-12-31", max_label=10)
    assert b["label"] == "PAUSE · xxxxxxxxx…"
    (b,) = vigueur.bandes_pauses(
        [{"date_debut": "2026-01-02", "date_fin": "2026-01-03", "raison": ""}],
        "2026-01-01",
        "2026-12-31",
    )
    assert b["label"] == "PAUSE"


# ── jalons du macro-cycle ────────────────────────────────────────────────────

PHASES = [
    {"Phase": "Hiver", "Début": "2026-12-21", "Fin": "2027-03-19", "Focus": "Force"},
    {"Phase": "Automne", "Début": "2026-09-23", "Fin": "2026-12-20", "Focus": "Vitesse"},
    {"Phase": "Printemps", "Début": "2027-03-20", "Fin": "2027-06-20", "Focus": "VO2max"},
]


def _t(i, echeance):
    return {"id": i, "titre": f"t{i}", "date_echeance": echeance, "statut": "todo"}


def test_jalons_rattaches_a_la_phase_de_leur_echeance():
    taches = [_t(1, "2026-12-20"), _t(2, "2026-12-21"), _t(3, "2027-03-19"), _t(4, "2027-06-20")]
    groupes, autres = vigueur.grouper_jalons(PHASES, taches)
    assert [p["Phase"] for p, _ in groupes] == ["Automne", "Hiver", "Printemps"]  # triées par début
    assert [[t["id"] for t in j] for _, j in groupes] == [[1], [2, 3], [4]]
    assert autres == []


def test_echeance_a_la_jointure_ne_compte_qu_une_fois():
    groupes, _ = vigueur.grouper_jalons(PHASES, [_t(1, "2027-03-20")])
    assert [len(j) for _, j in groupes] == [0, 0, 1]


def test_jalons_sans_echeance_ou_hors_phases_vont_dans_autres():
    taches = [_t(1, None), _t(2, "2026-01-01"), _t(3, "2028-01-01"), _t(4, "2027-01-15T10:00")]
    groupes, autres = vigueur.grouper_jalons(PHASES, taches)
    assert sorted(t["id"] for t in autres) == [1, 2, 3]
    assert [t["id"] for t in groupes[1][1]] == [4]  # échéance datetime tronquée au jour


def test_jalons_tries_par_echeance_dans_la_phase():
    taches = [_t(1, "2027-03-01"), _t(2, "2027-01-10"), _t(3, "2027-02-01")]
    groupes, _ = vigueur.grouper_jalons(PHASES, taches)
    assert [t["id"] for t in groupes[1][1]] == [2, 3, 1]


def test_sans_phase_tout_est_dans_autres():
    groupes, autres = vigueur.grouper_jalons([], [_t(1, "2026-12-20")])
    assert groupes == [] and [t["id"] for t in autres] == [1]
