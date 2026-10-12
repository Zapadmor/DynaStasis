"""Suivi de projets : projet → phases ordonnées → tâches à cocher (tables projets*).

La phase courante d'un projet est la première phase (par `ordre`) qui compte encore au moins
une tâche non cochée. Les phases sans tâche sont ignorées pour ce calcul.
"""

from __future__ import annotations

from src.database.connection import db_session
from src.repositories import projets as repo

STATUTS = ("en_cours", "en_pause", "termine", "abandonne")


def projets_en_cours() -> list[dict]:
    """Projets au statut « en_cours », avec progression et phase courante (tâches incluses)."""
    with db_session() as conn:
        result = []
        for projet in repo.liste_par_statut(conn, "en_cours"):
            total, faites = repo.progression(conn, projet["id"])
            phase = repo.phase_courante(conn, projet["id"])
            if phase is not None:
                phase["taches"] = repo.taches_de_phase(conn, phase["id"])
            result.append(
                {
                    **projet,
                    "total": total,
                    "faites": faites,
                    "phase": phase,
                    "phases": repo.phases_avec_progression(conn, projet["id"]),
                }
            )
    return result


def set_tache(tache_id: int, fait: bool) -> None:
    with db_session() as conn:
        repo.cocher_tache(conn, tache_id, fait)


def creer_projet(titre: str, description: str | None = None, objectif_id: int | None = None) -> int:
    with db_session() as conn:
        return repo.inserer_projet(conn, titre, description or None, objectif_id)


def ajouter_phase(
    projet_id: int,
    titre: str,
    objectif: str | None = None,
    prochaine_etape: str | None = None,
    notes: list[tuple[str, str]] | None = None,
) -> int:
    with db_session() as conn:
        return repo.inserer_phase(
            conn, projet_id, titre, objectif or None, prochaine_etape or None, notes
        )


def ajouter_tache(phase_id: int, libelle: str, fait: bool = False) -> int:
    with db_session() as conn:
        return repo.inserer_tache(conn, phase_id, libelle, fait)


def changer_statut(projet_id: int, statut: str) -> None:
    if statut not in STATUTS:
        raise ValueError(f"Statut inconnu : {statut}")
    with db_session() as conn:
        repo.maj_statut(conn, projet_id, statut)


def projets_gerables() -> list[dict]:
    with db_session() as conn:
        return repo.gerables(conn)


def phases_gerables() -> list[dict]:
    with db_session() as conn:
        return repo.phases_gerables(conn)
