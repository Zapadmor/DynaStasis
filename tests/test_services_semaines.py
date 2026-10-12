"""Fonctions pures de `services.semaines` et requêtes de `repositories.semaines`."""

from __future__ import annotations

import pytest

from src.repositories import semaines as repo
from src.services import semaines


@pytest.mark.parametrize(
    ("date", "debut", "libelle"),
    [
        ("2026-03-05", "2026-03-02", "Audit S10 – 02/03/2026"),
        ("2026-03-02", "2026-03-02", "Audit S10 – 02/03/2026"),
        ("2026-03-08", "2026-03-02", "Audit S10 – 02/03/2026"),
        ("2026-01-01", "2025-12-29", "Audit S01 – 29/12/2025"),  # semaine ISO à cheval sur l'année
    ],
)
def test_debut_et_libelle(date, debut, libelle):
    assert semaines.debut_et_libelle(date) == (debut, libelle)


@pytest.mark.parametrize(
    ("actuel", "precedent", "attendu"),
    [(60.0, 55.0, 5.0), (50.04, 55.0, -4.96 + 0.0), (None, 55.0, None), (60.0, None, None)],
)
def test_delta_hrv(actuel, precedent, attendu):
    assert semaines.delta_hrv(actuel, precedent) == (None if attendu is None else round(attendu, 1))


def test_repository_semaine_absente_puis_creee(conn):
    assert repo.id_par_debut(conn, "2026-03-02") is None
    wid = repo.inserer(conn, "2026-03-02", "Audit S10", "ecole", False)
    assert repo.id_par_debut(conn, "2026-03-02") == wid


def test_repository_gel_chevauchant(conn):
    conn.execute(
        "INSERT INTO system_freezes (date_debut, date_fin, raison) VALUES ('2026-03-04', '2026-03-05', 'x')"
    )
    assert repo.est_gelee(conn, "2026-03-02")
    assert not repo.est_gelee(conn, "2026-03-09")
