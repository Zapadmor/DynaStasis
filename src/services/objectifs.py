"""Objectifs et tâches de la Forge."""

from __future__ import annotations

from src.database.connection import db_session
from src.repositories import objectifs as repo


def charger_objectifs() -> tuple[list[dict], str | None]:
    """(objectifs non abandonnés, message d'erreur si la base n'est pas prête)."""
    try:
        with db_session() as conn:
            return repo.actifs(conn), None
    except Exception as e:
        return [], str(e)


def charger_taches(objectif_id: int) -> list[dict]:
    try:
        with db_session() as conn:
            return repo.taches(conn, objectif_id)
    except Exception:
        return []


def creer_objectif(
    titre: str, pilier: str, date_cible: str | None, description: str, priorite: int
) -> None:
    with db_session() as conn:
        repo.inserer(conn, titre, pilier, date_cible or None, description or None, priorite)


def archiver_objectif(objectif_id: int) -> None:
    with db_session() as conn:
        repo.archiver(conn, objectif_id)


def creer_tache(objectif_id: int, titre: str, priorite: int, date_echeance: str | None) -> None:
    with db_session() as conn:
        repo.inserer_tache(conn, objectif_id, titre, priorite, date_echeance or None)


def cocher_tache(tache_id: int, fait: bool) -> None:
    with db_session() as conn:
        repo.maj_statut_tache(conn, tache_id, fait)


def supprimer_tache(tache_id: int) -> None:
    """Annule la tâche (elle n'est plus listée mais reste en base)."""
    with db_session() as conn:
        repo.annuler_tache(conn, tache_id)
