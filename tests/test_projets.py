"""Suivi de projets : phase courante = première phase avec des tâches à valider."""

from __future__ import annotations

import pytest

from src.core import projets
from src.database import connection


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "DB_PATH", tmp_path / "test.db")
    connection.init_db()


def _projet_a_deux_phases():
    pid = projets.creer_projet("Projet test", "desc")
    p1 = projets.ajouter_phase(pid, "Phase 1", objectif="obj", notes=[("Titre", "Corps")])
    p2 = projets.ajouter_phase(pid, "Phase 2")
    t1 = projets.ajouter_tache(p1, "A")
    t2 = projets.ajouter_tache(p1, "B")
    t3 = projets.ajouter_tache(p2, "C")
    return pid, (p1, p2), (t1, t2, t3)


def test_phase_courante_avance_quand_les_cases_sont_cochees(db):
    _, _, (t1, t2, t3) = _projet_a_deux_phases()

    (p,) = projets.projets_en_cours()
    assert p["phase"]["titre"] == "Phase 1"
    assert (p["faites"], p["total"]) == (0, 3)
    assert p["phase"]["notes"] == [["Titre", "Corps"]]

    projets.set_tache(t1, True)
    assert projets.projets_en_cours()[0]["phase"]["titre"] == "Phase 1"

    projets.set_tache(t2, True)
    (p,) = projets.projets_en_cours()
    assert p["phase"]["titre"] == "Phase 2"
    assert [t["libelle"] for t in p["phase"]["taches"]] == ["C"]

    projets.set_tache(t3, True)
    (p,) = projets.projets_en_cours()
    assert p["phase"] is None and (p["faites"], p["total"]) == (3, 3)


def test_decocher_revient_a_la_phase_precedente(db):
    _, _, (t1, t2, t3) = _projet_a_deux_phases()
    for t in (t1, t2):
        projets.set_tache(t, True)
    projets.set_tache(t1, False)
    assert projets.projets_en_cours()[0]["phase"]["titre"] == "Phase 1"


def test_phase_sans_tache_est_ignoree(db):
    pid = projets.creer_projet("P")
    projets.ajouter_phase(pid, "Vide")
    p2 = projets.ajouter_phase(pid, "Avec tâche")
    projets.ajouter_tache(p2, "x")
    assert projets.projets_en_cours()[0]["phase"]["titre"] == "Avec tâche"


def test_seuls_les_projets_en_cours_sont_listes(db):
    pid, _, _ = _projet_a_deux_phases()
    autre = projets.creer_projet("En pause")
    projets.changer_statut(autre, "en_pause")
    assert [p["titre"] for p in projets.projets_en_cours()] == ["Projet test"]
    assert {p["titre"] for p in projets.projets_gerables()} == {"Projet test", "En pause"}

    projets.changer_statut(pid, "termine")
    assert projets.projets_en_cours() == []
    with pytest.raises(ValueError):
        projets.changer_statut(pid, "inconnu")


def test_phases_gerables_et_ordre_des_phases(db):
    _projet_a_deux_phases()
    assert [x["phase"] for x in projets.phases_gerables()] == ["Phase 1", "Phase 2"]
