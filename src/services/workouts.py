"""Séances d'entraînement : manipulation des listes d'exercices et de séries en cours de saisie."""

from __future__ import annotations


def renumber_sets(sets: list[dict]) -> None:
    """Renumérote les séries de travail (1, 2, 3…) ; échauffement (W) et échec (F) sont conservés."""
    counter = 1
    for s in sets:
        if s["set_type"] not in ("W", "F"):
            s["set_type"] = str(counter)
            counter += 1


def reposition(exercises: list[dict]) -> None:
    """Réécrit `position` (à partir de 1) selon l'ordre de la liste."""
    for i, ex in enumerate(exercises):
        ex["position"] = i + 1
