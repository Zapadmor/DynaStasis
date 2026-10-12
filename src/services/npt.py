"""Notes pour trop tard : proches et notes datées."""

from __future__ import annotations

from src.database.connection import db_session
from src.repositories import npt as repo


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
