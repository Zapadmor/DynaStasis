"""Notes pour trop tard : proches et notes datées."""

from __future__ import annotations

from src.database.connection import db_session
from src.repositories import npt as repo

TYPES_CHANTIER = (
    "RETEX",
    "Chantier psy",
    "Exercice",
    "Écueil",
    "Défi relationnel",
    "Qualité",
    "Défaut",
)
STATUTS_CHANTIER = ("Ouvert", "En cours", "Clos")


def tables_pretes() -> bool:
    with db_session() as conn:
        return repo.tables_pretes(conn)


def personnes() -> list[dict]:
    with db_session() as conn:
        return repo.personnes(conn)


def notes(personne_id: int) -> list[dict]:
    with db_session() as conn:
        return repo.notes(conn, personne_id)


def ajouter_note(personne_id: int, date_note: str, contenu: str) -> None:
    with db_session() as conn:
        repo.ajouter_note(conn, personne_id, date_note, contenu)


def ajouter_personne(
    prenom: str, nom: str, liens: list[str], etat: str, proximite: int | None
) -> int:
    with db_session() as conn:
        return repo.ajouter_personne(conn, prenom, nom, liens, etat, proximite)


def chantiers_prets() -> bool:
    with db_session() as conn:
        return repo.chantiers_prets(conn)


def chantiers() -> list[dict]:
    with db_session() as conn:
        return repo.chantiers(conn)


def entrees(chantier_id: int) -> list[dict]:
    with db_session() as conn:
        return repo.entrees(conn, chantier_id)


def ajouter_chantier(personne_id: int | None, type_: str, titre: str, description: str = "") -> int:
    if type_ not in TYPES_CHANTIER:
        raise ValueError(f"Type de chantier inconnu : {type_}")
    with db_session() as conn:
        return repo.ajouter_chantier(conn, personne_id, type_, titre, description)


def changer_statut_chantier(chantier_id: int, statut: str) -> None:
    if statut not in STATUTS_CHANTIER:
        raise ValueError(f"Statut inconnu : {statut}")
    with db_session() as conn:
        repo.changer_statut_chantier(conn, chantier_id, statut)


def ajouter_entree(chantier_id: int, date_entree: str, contenu: str) -> None:
    with db_session() as conn:
        repo.ajouter_entree(conn, chantier_id, date_entree, contenu)
