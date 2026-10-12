"""Services Vigueur : zones de forme, phases, lecture de la charge, listes de séries."""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from src.services import vigueur, workouts


@pytest.mark.parametrize(
    ("tsb", "attendu"),
    [
        (None, "—"),
        (-45, "SURMENAGE"),
        (-30, "OPTIMAL"),
        (-10, "ZONE GRISE"),
        (4.9, "ZONE GRISE"),
        (5, "FRESH"),
        (19.9, "FRESH"),
        (20, "TRANSITION"),
    ],
)
def test_statut_forme(tsb, attendu):
    assert vigueur.statut_forme(tsb) == attendu


def test_statut_phase_bornes_incluses():
    jour = datetime.date(2026, 6, 15)
    assert vigueur.statut_phase("2026-06-16", "2026-07-01", jour) == "À VENIR"
    assert vigueur.statut_phase("2026-06-01", "2026-06-15", jour) == "EN COURS"
    assert vigueur.statut_phase("2026-06-15", "2026-07-01", jour) == "EN COURS"
    assert vigueur.statut_phase("2026-05-01", "2026-06-14", jour) == "PASSÉ"


def test_libelle_jour():
    assert vigueur.libelle_jour("2026-10-05") == "05/10"


def test_renumber_sets_garde_echauffement_et_echec():
    sets = [{"set_type": t} for t in ("W", "1", "2", "F", "3")]
    workouts.renumber_sets(sets)
    assert [s["set_type"] for s in sets] == ["W", "1", "2", "F", "3"]
    sets = [{"set_type": t} for t in ("W", "2", "3")]
    workouts.renumber_sets(sets)
    assert [s["set_type"] for s in sets] == ["W", "1", "2"]


def test_reposition():
    exos = [{"name": "a"}, {"name": "b"}]
    workouts.reposition(exos)
    assert [e["position"] for e in exos] == [1, 2]


def test_donnees_charge_base_vide(db):
    assert vigueur.donnees_charge() == ([], [], [])
    assert vigueur.ecran_top_apps() == []
    assert vigueur.ecran_total_heures() is None
    assert vigueur.resume_seance(1) is None


def test_donnees_charge_ordre_chronologique(demo_db):
    semaines, jours, quotidien = vigueur.donnees_charge()
    assert semaines and len(jours) <= 7 and quotidien
    for lignes, cle in ((semaines, "week_start"), (jours, "date_entry"), (quotidien, "date_entry")):
        dates = [r[cle] for r in lignes]
        assert dates == sorted(dates)


def test_petits_graphiques_7j_axe_en_categories(monkeypatch):
    """Les étiquettes « jj/mm » ne doivent pas être lues comme des dates (« Mar 2010 »)."""
    from src.app.views.vigueur import recuperation

    figures = []
    monkeypatch.setattr(recuperation.st, "plotly_chart", lambda fig, **kw: figures.append(fig))
    df = pd.DataFrame({"date_entry": ["2026-10-03", "2026-10-04"], "hrv": [60.0, 62.0]})
    recuperation._mini_bars(df, "hrv", "#fff")
    (fig,) = figures
    assert list(fig.data[0].x) == ["03/10", "04/10"]
    assert fig.layout.xaxis.type == "category"
